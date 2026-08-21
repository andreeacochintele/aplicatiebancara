export const INDUSTRY_OPTIONS = [
  "Technology",
  "Healthcare",
  "Finance & Banking",
  "Education",
  "Retail & E-commerce",
  "Manufacturing",
  "Construction",
  "Real Estate",
  "Hospitality & Tourism",
  "Transportation & Logistics",
  "Government & Public Sector",
  "Non-profit",
  "Agriculture",
  "Energy & Utilities",
  "Media & Entertainment",
  "Legal Services",
  "Consulting",
  "Telecommunications",
];

export const INCOME_SOURCE_OPTIONS = [
  "Salary",
  "Business income",
  "Freelance / self-employed income",
  "Investments",
  "Pension",
  "Rental income",
  "Family support",
];

// Employment statuses for which Employer/Industry don't apply and are hidden in the wizard.
export const EMPLOYMENT_STATUSES_WITHOUT_EMPLOYER = new Set(["UNEMPLOYED", "STUDENT", "RETIRED"]);
