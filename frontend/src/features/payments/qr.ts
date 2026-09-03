/**
 * Minimal QR Code encoder (ISO/IEC 18004): byte mode, error-correction level
 * M, versions 1-10. Produces a module matrix that a phone camera can read.
 *
 * Written in-repo rather than pulled from npm on purpose. The frontend
 * container mounts node_modules as an anonymous volume (docker-compose.yml),
 * so a package added to package.json is invisible until the image is rebuilt,
 * and one installed inside a running container disappears the next time that
 * container is recreated. CI also has no npm step at all. A dependency here
 * would break for every teammate on `git pull`; this file does not.
 *
 * Scope is deliberately narrow: byte mode covers any UTF-8 payload, level M
 * is the usual balance of density against damage tolerance, and version 10
 * at level M already holds 216 bytes - far more than the payment-request
 * identifiers and links this app encodes.
 */

export type QrMatrix = boolean[][];

/** Level M, per version 1-10:
 *  [ecCodewordsPerBlock, group1Blocks, group1DataCodewords, group2Blocks, group2DataCodewords]
 *  Data codeword counts are per block, not per group. */
const EC_TABLE_M: ReadonlyArray<readonly [number, number, number, number, number]> = [
  [10, 1, 16, 0, 0],
  [16, 1, 28, 0, 0],
  [26, 1, 44, 0, 0],
  [18, 2, 32, 0, 0],
  [24, 2, 43, 0, 0],
  [16, 4, 27, 0, 0],
  [18, 4, 31, 0, 0],
  [22, 2, 38, 2, 39],
  [22, 3, 36, 2, 37],
  [26, 4, 43, 1, 44],
];

/** Row/column centres of the alignment patterns, per version 1-10. */
const ALIGNMENT_CENTRES: ReadonlyArray<readonly number[]> = [
  [],
  [6, 18],
  [6, 22],
  [6, 26],
  [6, 30],
  [6, 34],
  [6, 22, 38],
  [6, 24, 42],
  [6, 26, 46],
  [6, 28, 50],
];

const MAX_VERSION = EC_TABLE_M.length;

// ---------------------------------------------------------------------------
// GF(256) arithmetic, primitive polynomial 0x11D, generator 2.
// ---------------------------------------------------------------------------

const EXP = new Uint8Array(512);
const LOG = new Uint8Array(256);

(function buildTables() {
  let x = 1;
  for (let i = 0; i < 255; i += 1) {
    EXP[i] = x;
    LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i += 1) EXP[i] = EXP[i - 255];
})();

function gfMul(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return EXP[LOG[a] + LOG[b]];
}

/** Generator polynomial for `degree` error-correction codewords. */
function generatorPoly(degree: number): number[] {
  let poly = [1];
  for (let i = 0; i < degree; i += 1) {
    const next = new Array<number>(poly.length + 1).fill(0);
    for (let j = 0; j < poly.length; j += 1) {
      next[j] ^= poly[j];
      next[j + 1] ^= gfMul(poly[j], EXP[i]);
    }
    poly = next;
  }
  return poly;
}

/** Remainder of `data` divided by the generator polynomial: the EC codewords. */
function reedSolomon(data: number[], ecCount: number): number[] {
  const generator = generatorPoly(ecCount);
  const remainder = new Array<number>(ecCount).fill(0);
  for (const byte of data) {
    const factor = byte ^ remainder[0];
    remainder.shift();
    remainder.push(0);
    for (let i = 0; i < ecCount; i += 1) {
      remainder[i] ^= gfMul(generator[i + 1], factor);
    }
  }
  return remainder;
}

// ---------------------------------------------------------------------------
// Bit buffer
// ---------------------------------------------------------------------------

class BitBuffer {
  readonly bits: number[] = [];

  put(value: number, length: number): void {
    for (let i = length - 1; i >= 0; i -= 1) {
      this.bits.push((value >>> i) & 1);
    }
  }
}

// ---------------------------------------------------------------------------
// Encoding
// ---------------------------------------------------------------------------

function totalDataCodewords(version: number): number {
  const [, g1Blocks, g1Words, g2Blocks, g2Words] = EC_TABLE_M[version - 1];
  return g1Blocks * g1Words + g2Blocks * g2Words;
}

/** Smallest version 1-10 whose level-M capacity fits `byteLength`. */
function chooseVersion(byteLength: number): number {
  for (let version = 1; version <= MAX_VERSION; version += 1) {
    // 4 mode bits + character-count indicator + payload, in bits.
    const countBits = version < 10 ? 8 : 16;
    const needed = 4 + countBits + byteLength * 8;
    if (needed <= totalDataCodewords(version) * 8) return version;
  }
  throw new Error(`QR payload too long: ${byteLength} bytes exceeds version ${MAX_VERSION} at level M`);
}

/** Mode indicator, length, payload, terminator, padding - as codewords. */
function buildDataCodewords(bytes: Uint8Array, version: number): number[] {
  const capacity = totalDataCodewords(version);
  const buffer = new BitBuffer();
  buffer.put(0b0100, 4); // byte mode
  buffer.put(bytes.length, version < 10 ? 8 : 16);
  for (const byte of bytes) buffer.put(byte, 8);

  // Terminator: up to four zero bits, truncated if capacity runs out.
  const capacityBits = capacity * 8;
  const terminator = Math.min(4, capacityBits - buffer.bits.length);
  buffer.put(0, terminator);
  // Pad to a whole codeword, then alternate the two specified pad bytes.
  while (buffer.bits.length % 8 !== 0) buffer.bits.push(0);

  const codewords: number[] = [];
  for (let i = 0; i < buffer.bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j += 1) byte = (byte << 1) | buffer.bits[i + j];
    codewords.push(byte);
  }
  const PAD = [0xec, 0x11];
  for (let i = 0; codewords.length < capacity; i += 1) codewords.push(PAD[i % 2]);
  return codewords;
}

/** Split into blocks, compute EC per block, then interleave both sets. */
function interleave(dataCodewords: number[], version: number): number[] {
  const [ecPerBlock, g1Blocks, g1Words, g2Blocks, g2Words] = EC_TABLE_M[version - 1];

  const dataBlocks: number[][] = [];
  let offset = 0;
  for (let i = 0; i < g1Blocks; i += 1) {
    dataBlocks.push(dataCodewords.slice(offset, offset + g1Words));
    offset += g1Words;
  }
  for (let i = 0; i < g2Blocks; i += 1) {
    dataBlocks.push(dataCodewords.slice(offset, offset + g2Words));
    offset += g2Words;
  }
  const ecBlocks = dataBlocks.map((block) => reedSolomon(block, ecPerBlock));

  const result: number[] = [];
  const longestData = Math.max(...dataBlocks.map((block) => block.length));
  for (let i = 0; i < longestData; i += 1) {
    for (const block of dataBlocks) {
      if (i < block.length) result.push(block[i]);
    }
  }
  for (let i = 0; i < ecPerBlock; i += 1) {
    for (const block of ecBlocks) result.push(block[i]);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Matrix construction
// ---------------------------------------------------------------------------

type Grid = { modules: (boolean | null)[][]; reserved: boolean[][]; size: number };

function createGrid(version: number): Grid {
  const size = version * 4 + 17;
  return {
    size,
    modules: Array.from({ length: size }, () => new Array<boolean | null>(size).fill(null)),
    reserved: Array.from({ length: size }, () => new Array<boolean>(size).fill(false)),
  };
}

function place(grid: Grid, row: number, col: number, dark: boolean): void {
  grid.modules[row][col] = dark;
  grid.reserved[row][col] = true;
}

function drawFinder(grid: Grid, row: number, col: number): void {
  // 7x7 finder plus its one-module separator, clipped at the grid edges.
  for (let r = -1; r <= 7; r += 1) {
    for (let c = -1; c <= 7; c += 1) {
      const rr = row + r;
      const cc = col + c;
      if (rr < 0 || rr >= grid.size || cc < 0 || cc >= grid.size) continue;
      const onOuterRing = (r === 0 || r === 6) && c >= 0 && c <= 6;
      const onOuterCol = (c === 0 || c === 6) && r >= 0 && r <= 6;
      const inCore = r >= 2 && r <= 4 && c >= 2 && c <= 4;
      place(grid, rr, cc, onOuterRing || onOuterCol || inCore);
    }
  }
}

function drawAlignment(grid: Grid, version: number): void {
  const centres = ALIGNMENT_CENTRES[version - 1];
  for (const row of centres) {
    for (const col of centres) {
      // The three finder corners take precedence over alignment patterns.
      if (grid.reserved[row][col]) continue;
      for (let r = -2; r <= 2; r += 1) {
        for (let c = -2; c <= 2; c += 1) {
          const ring = Math.max(Math.abs(r), Math.abs(c));
          place(grid, row + r, col + c, ring !== 1);
        }
      }
    }
  }
}

function drawTiming(grid: Grid): void {
  for (let i = 8; i < grid.size - 8; i += 1) {
    const dark = i % 2 === 0;
    if (!grid.reserved[6][i]) place(grid, 6, i, dark);
    if (!grid.reserved[i][6]) place(grid, i, 6, dark);
  }
}

/** Marks the format-info strips (and the always-dark module) as occupied so
 *  data placement skips them; the real bits are written after masking. */
function reserveFormatAreas(grid: Grid, version: number): void {
  for (let i = 0; i <= 8; i += 1) {
    if (!grid.reserved[8][i]) place(grid, 8, i, false);
    if (!grid.reserved[i][8]) place(grid, i, 8, false);
  }
  for (let i = 0; i < 8; i += 1) {
    if (!grid.reserved[8][grid.size - 1 - i]) place(grid, 8, grid.size - 1 - i, false);
    if (!grid.reserved[grid.size - 1 - i][8]) place(grid, grid.size - 1 - i, 8, false);
  }
  place(grid, grid.size - 8, 8, true); // the fixed dark module

  if (version >= 7) {
    for (let i = 0; i < 6; i += 1) {
      for (let j = 0; j < 3; j += 1) {
        place(grid, grid.size - 11 + j, i, false);
        place(grid, i, grid.size - 11 + j, false);
      }
    }
  }
}

/** Zigzag placement: two-module columns, right to left, skipping column 6. */
function placeData(grid: Grid, codewords: number[]): void {
  let bitIndex = 0;
  let upward = true;
  for (let right = grid.size - 1; right > 0; right -= 2) {
    if (right === 6) right -= 1; // the vertical timing column is never data
    for (let step = 0; step < grid.size; step += 1) {
      const row = upward ? grid.size - 1 - step : step;
      for (let c = 0; c < 2; c += 1) {
        const col = right - c;
        if (grid.reserved[row][col]) continue;
        const byte = codewords[bitIndex >>> 3];
        // Any bits past the payload are the specified remainder bits: zero.
        const bit = byte === undefined ? 0 : (byte >>> (7 - (bitIndex & 7))) & 1;
        grid.modules[row][col] = bit === 1;
        bitIndex += 1;
      }
    }
    upward = !upward;
  }
}

const MASKS: ReadonlyArray<(row: number, col: number) => boolean> = [
  (r, c) => (r + c) % 2 === 0,
  (r) => r % 2 === 0,
  (_r, c) => c % 3 === 0,
  (r, c) => (r + c) % 3 === 0,
  (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
  (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
  (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
  (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
];

function applyMask(grid: Grid, maskIndex: number): boolean[][] {
  const mask = MASKS[maskIndex];
  return grid.modules.map((row, r) =>
    row.map((value, c) => {
      const dark = value === true;
      // Function patterns are never masked.
      return grid.reserved[r][c] ? dark : dark !== mask(r, c);
    }),
  );
}

function formatBits(maskIndex: number): number {
  // 5 data bits (EC level M = 0b00, then the mask), BCH(15,5), XOR 0x5412.
  let value = (0b00 << 3) | maskIndex;
  let bch = value << 10;
  for (let i = 14; i >= 10; i -= 1) {
    if ((bch >>> i) & 1) bch ^= 0b10100110111 << (i - 10);
  }
  value = ((value << 10) | bch) ^ 0b101010000010010;
  return value;
}

function versionBits(version: number): number {
  // Golay(18,6): 6 version bits plus a BCH remainder under the generator
  // x^12 + x^11 + x^10 + x^9 + x^8 + x^5 + x^2 + 1.
  let bch = version << 12;
  for (let i = 17; i >= 12; i -= 1) {
    if ((bch >>> i) & 1) bch ^= 0b1111100100101 << (i - 12);
  }
  return (version << 12) | bch;
}

function writeFormatAndVersion(matrix: boolean[][], version: number, maskIndex: number): void {
  const size = matrix.length;
  const format = formatBits(maskIndex);
  const bitAt = (i: number) => ((format >>> i) & 1) === 1;

  // The 15 bits run most-significant first, so bit 14 sits at (8,0). Copy 1
  // walks row 8 rightwards and then climbs column 8, skipping row/column 6
  // because the timing patterns own those.
  for (let i = 0; i <= 5; i += 1) matrix[8][i] = bitAt(14 - i);
  matrix[8][7] = bitAt(8);
  matrix[8][8] = bitAt(7);
  matrix[7][8] = bitAt(6);
  for (let i = 0; i <= 5; i += 1) matrix[i][8] = bitAt(i);

  // Copy 2 is split: the high 7 bits climb column 8 from the bottom edge, the
  // low 8 run rightwards along row 8 to the right edge.
  for (let i = 0; i <= 6; i += 1) matrix[size - 1 - i][8] = bitAt(14 - i);
  for (let i = 0; i <= 7; i += 1) matrix[8][size - 8 + i] = bitAt(7 - i);
  matrix[size - 8][8] = true; // the fixed dark module

  if (version >= 7) {
    const info = versionBits(version);
    for (let i = 0; i < 18; i += 1) {
      const bit = ((info >>> i) & 1) === 1;
      const row = Math.floor(i / 3);
      const col = size - 11 + (i % 3);
      matrix[row][col] = bit;
      matrix[col][row] = bit;
    }
  }
}

// ---------------------------------------------------------------------------
// Mask penalty scoring (ISO/IEC 18004 section 8.8.2)
// ---------------------------------------------------------------------------

function penalty(matrix: boolean[][]): number {
  const size = matrix.length;
  let score = 0;

  // Rule 1: runs of five or more same-coloured modules in a row or column.
  for (let i = 0; i < size; i += 1) {
    for (const readRow of [true, false]) {
      let runColour = matrix[i][0];
      let runLength = 1;
      if (!readRow) runColour = matrix[0][i];
      for (let j = 1; j < size; j += 1) {
        const value = readRow ? matrix[i][j] : matrix[j][i];
        if (value === runColour) {
          runLength += 1;
        } else {
          if (runLength >= 5) score += runLength - 2;
          runColour = value;
          runLength = 1;
        }
      }
      if (runLength >= 5) score += runLength - 2;
    }
  }

  // Rule 2: every 2x2 block of one colour.
  for (let r = 0; r < size - 1; r += 1) {
    for (let c = 0; c < size - 1; c += 1) {
      const v = matrix[r][c];
      if (v === matrix[r][c + 1] && v === matrix[r + 1][c] && v === matrix[r + 1][c + 1]) score += 3;
    }
  }

  // Rule 3: the 1:1:3:1:1 finder-lookalike pattern, with four light modules
  // on either side, in any row or column.
  const A = [true, false, true, true, true, false, true, false, false, false, false];
  const B = [false, false, false, false, true, false, true, true, true, false, true];
  for (let i = 0; i < size; i += 1) {
    for (let j = 0; j + 11 <= size; j += 1) {
      let rowMatchesA = true;
      let rowMatchesB = true;
      let colMatchesA = true;
      let colMatchesB = true;
      for (let k = 0; k < 11; k += 1) {
        if (matrix[i][j + k] !== A[k]) rowMatchesA = false;
        if (matrix[i][j + k] !== B[k]) rowMatchesB = false;
        if (matrix[j + k][i] !== A[k]) colMatchesA = false;
        if (matrix[j + k][i] !== B[k]) colMatchesB = false;
      }
      if (rowMatchesA) score += 40;
      if (rowMatchesB) score += 40;
      if (colMatchesA) score += 40;
      if (colMatchesB) score += 40;
    }
  }

  // Rule 4: deviation of the dark-module proportion from 50%.
  let dark = 0;
  for (const row of matrix) for (const value of row) if (value) dark += 1;
  const percent = (dark * 100) / (size * size);
  score += Math.floor(Math.abs(percent - 50) / 5) * 10;

  return score;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Encodes `text` and returns the module matrix, `true` meaning a dark module.
 * The quiet zone is not included - the renderer adds it.
 *
 * @throws if the payload exceeds version 10 at level M (216 bytes).
 */
export function encodeQr(text: string): QrMatrix {
  const bytes = new TextEncoder().encode(text);
  const version = chooseVersion(bytes.length);
  const codewords = interleave(buildDataCodewords(bytes, version), version);

  const grid = createGrid(version);
  drawFinder(grid, 0, 0);
  drawFinder(grid, 0, grid.size - 7);
  drawFinder(grid, grid.size - 7, 0);
  drawAlignment(grid, version);
  drawTiming(grid);
  reserveFormatAreas(grid, version);
  placeData(grid, codewords);

  let best: boolean[][] | null = null;
  let bestScore = Infinity;
  for (let maskIndex = 0; maskIndex < MASKS.length; maskIndex += 1) {
    const candidate = applyMask(grid, maskIndex);
    writeFormatAndVersion(candidate, version, maskIndex);
    const score = penalty(candidate);
    if (score < bestScore) {
      bestScore = score;
      best = candidate;
    }
  }
  // MASKS is non-empty, so the loop always assigns; this keeps the type honest.
  if (best === null) throw new Error("QR mask selection produced no candidate");
  return best;
}
