from datetime import date

import pytest

from app.users.mrz import (
    MrzFormatError,
    compute_check_digit,
    parse_td1,
    parse_td2,
    reconstruct_romanian_cnp_from_td2,
)


def _checked(data: str) -> str:
    """`data` followed by its own correct ICAO check digit."""
    return f"{data}{compute_check_digit(data)}"


def test_compute_check_digit_matches_known_icao_example():
    # Textbook ICAO 9303 example (document number "L898902C3" -> check digit 6).
    assert compute_check_digit("L898902C3") == 6


class TestParseTd1:
    def _build(
        self,
        *,
        document_number: str = "RT1234567",
        date_of_birth: str = "900101",
        sex: str = "F",
        date_of_expiry: str = "300101",
        nationality: str = "ROU",
        optional_data_1: str = "<" * 15,
        optional_data_2: str = "<" * 11,
        surname: str = "IONESCU",
        given_names: str = "MARIA<ELENA",
    ) -> tuple[str, str, str]:
        line1 = "I<" + "ROU" + _checked(document_number) + optional_data_1
        line2_prefix = _checked(date_of_birth) + sex + _checked(date_of_expiry) + nationality + optional_data_2
        composite_input = line1[5:30] + line2_prefix[0:7] + line2_prefix[8:15] + line2_prefix[18:29]
        line2 = line2_prefix + str(compute_check_digit(composite_input))
        name_field = f"{surname}<<{given_names}"
        line3 = name_field + "<" * (30 - len(name_field))
        assert len(line1) == 30 and len(line2) == 30 and len(line3) == 30
        return line1, line2, line3

    def test_valid_document_parses_and_all_checks_pass(self):
        line1, line2, line3 = self._build()
        result = parse_td1(line1, line2, line3)

        assert result.document_number == "RT1234567"
        assert result.date_of_birth == date(1990, 1, 1)
        assert result.date_of_expiry == date(2030, 1, 1)
        assert result.sex == "F"
        assert result.nationality == "ROU"
        assert result.surname == "IONESCU"
        assert result.given_names == "MARIA ELENA"
        assert result.all_checks_valid is True

    def test_detects_bad_document_number_checksum(self):
        line1, line2, line3 = self._build()
        # Flip the document number's check digit (position 15, index 14).
        corrupted_digit = "0" if line1[14] != "0" else "1"
        line1 = line1[:14] + corrupted_digit + line1[15:]

        result = parse_td1(line1, line2, line3)

        assert result.document_number_check_valid is False
        assert result.all_checks_valid is False
        # Unrelated fields are unaffected.
        assert result.date_of_birth == date(1990, 1, 1)

    def test_detects_bad_composite_checksum(self):
        line1, line2, line3 = self._build()
        corrupted_digit = "0" if line2[29] != "0" else "1"
        line2 = line2[:29] + corrupted_digit

        result = parse_td1(line1, line2, line3)

        assert result.composite_check_valid is False
        assert result.all_checks_valid is False

    def test_two_digit_year_after_current_year_resolves_to_1900s(self):
        # If today's two-digit year is, say, 26, a birth year of "30" can't be
        # 2030 (a future birth date) so it must resolve to 1930.
        future_looking_yy = f"{(date.today().year + 4) % 100:02d}0101"
        line1, line2, line3 = self._build(date_of_birth=future_looking_yy)

        result = parse_td1(line1, line2, line3)

        assert result.date_of_birth is not None
        assert result.date_of_birth.year == 1900 + int(future_looking_yy[0:2])

    def test_rejects_wrong_length_line(self):
        line1, line2, line3 = self._build()
        with pytest.raises(MrzFormatError):
            parse_td1(line1[:-1], line2, line3)

    def test_rejects_invalid_character(self):
        line1, line2, line3 = self._build()
        line1 = line1[:2] + "?" + line1[3:]
        with pytest.raises(MrzFormatError):
            parse_td1(line1, line2, line3)


class TestParseTd2:
    def _build(
        self,
        *,
        document_number: str = "RT1234567",
        nationality: str = "ROU",
        date_of_birth: str = "900101",
        sex: str = "F",
        date_of_expiry: str = "300101",
        optional_data: str = "<" * 7,
        surname: str = "IONESCU",
        given_names: str = "MARIA<ELENA",
    ) -> tuple[str, str]:
        name_field = f"{surname}<<{given_names}"
        line1 = "I<" + "ROU" + name_field + "<" * (36 - 5 - len(name_field))
        line2_prefix = (
            _checked(document_number) + nationality + _checked(date_of_birth) + sex + _checked(date_of_expiry) + optional_data
        )
        composite_input = line2_prefix[0:10] + line2_prefix[13:20] + line2_prefix[21:35]
        line2 = line2_prefix + str(compute_check_digit(composite_input))
        assert len(line1) == 36 and len(line2) == 36
        return line1, line2

    def test_valid_document_parses_and_all_checks_pass(self):
        line1, line2 = self._build()
        result = parse_td2(line1, line2)

        assert result.document_number == "RT1234567"
        assert result.surname == "IONESCU"
        assert result.given_names == "MARIA ELENA"
        assert result.date_of_birth == date(1990, 1, 1)
        assert result.date_of_expiry == date(2030, 1, 1)
        assert result.all_checks_valid is True

    def test_detects_bad_checksum(self):
        line1, line2 = self._build()
        corrupted_digit = "0" if line2[9] != "0" else "1"
        line2 = line2[:9] + corrupted_digit + line2[10:]

        result = parse_td2(line1, line2)

        assert result.document_number_check_valid is False
        assert result.all_checks_valid is False


class TestReconstructRomanianCnpFromTd2:
    def test_reconstructs_a_known_valid_cnp(self):
        # CNP "1900101123457" (already used/validated elsewhere in the test
        # suite): S=1, birth=1990-01-01 (YYMMDD "900101"), county+seq+check
        # = "12345" + "7". TD2's optional-data field holds it "without the
        # birth date": S + county+seq+check = "1" + "123457" = "1123457".
        line1, line2 = TestParseTd2()._build(optional_data="1123457")
        parsed = parse_td2(line1, line2)

        cnp = reconstruct_romanian_cnp_from_td2(parsed)

        assert cnp == "1900101123457"

    def test_returns_none_when_optional_data_is_the_wrong_shape(self):
        line1, line2 = TestParseTd2()._build(optional_data="<" * 7)
        parsed = parse_td2(line1, line2)

        assert reconstruct_romanian_cnp_from_td2(parsed) is None

    def test_returns_none_when_date_of_birth_could_not_be_parsed(self):
        line1, line2 = TestParseTd2()._build(date_of_birth="991301", optional_data="1123457")
        parsed = parse_td2(line1, line2)

        assert parsed.date_of_birth is None
        assert reconstruct_romanian_cnp_from_td2(parsed) is None
