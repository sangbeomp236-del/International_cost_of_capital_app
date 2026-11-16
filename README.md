# International Cost of Capital App

This Streamlit app compares a project's cost of equity and WACC in USD and in the currency of a selected country.

## Default Settings

- Industry: Software (System & Application)
- Target country: United States
- Project tax rate: U.S. tax rate
- Equity risk premium: 6.5%
- Target debt share: 30%

## Data Sources

The app uses the sources provided in the assignment.

### Industry Unlevered Beta

Aswath Damodaran:

https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls

The app downloads and reads the Damodaran Excel file directly and uses the Unlevered Beta for the selected U.S. industry.

A copy of `betas.xls` is also stored in the GitHub repository as a backup if the live download fails.

### Corporate Tax Rates

OECD Corporate Tax Statistics 2024:

https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html#chapter-d1e2342-08e74a33fb

The OECD publication page may block automated requests from Streamlit Cloud.

Therefore, the app downloads the underlying official OECD Excel data through the Statlink associated with the corporate tax-rate figure:

https://stat.link/0qkxo1

This is the underlying OECD data linked from the professor-provided OECD publication.

### USD BBB Borrowing Spread

Aswath Damodaran:

https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html

The app uses the Baa2/BBB borrowing spread for large non-financial service firms.

### 10-Year Government Bond Yields

Trading Economics:

https://tradingeconomics.com/bonds

The app first attempts to retrieve the 10-year government bond yield from the professor-provided Trading Economics bonds page.

If that page is dynamically rendered, the app uses the corresponding country government-bond page on the same Trading Economics website.

## Main Formulas

### Relevered Beta

beta_E = beta_U × [1 + (1 - tax rate) × D/E]

where:

D/E = Debt Share / (1 - Debt Share)

### USD Cost of Equity

Re = Rf + beta_E × ERP

### USD Pretax Borrowing Cost

Rd = Rf + s

where `s` is the USD BBB borrowing spread.

### Foreign-Currency Cost of Equity

1 + Re* = (1 + Re) × (1 + Rf*) / (1 + Rf)

### Foreign-Currency BBB Spread

s* = s × (1 + Rf*) / (1 + Rf)

### Foreign-Currency Pretax Borrowing Cost

Rd* = Rf* + s*

### WACC

WACC = (1 - d) × Re + d × Rd × (1 - tax rate)

## Manual Overrides

The user can manually override:

- Unlevered beta
- U.S. corporate tax rate
- Selected-country corporate tax rate
- USD BBB borrowing spread
- U.S. 10-year government yield
- Selected-country 10-year government yield
- Selected-country BBB borrowing spread

## Other Features

- Refresh source data button
- Industry selection
- Target-country selection
- Adjustable equity risk premium
- Adjustable target debt share
- Choice between U.S. and foreign corporate tax rate
- Side-by-side USD and foreign-currency results
- Calculation detail
- All-industry comparison
- Downloadable CSV results
- Source and date display

## Notes

The app uses the simplified international cost-of-capital formulas discussed in class.

External websites may occasionally change their page structure or block automated requests. Manual override controls are therefore available for all major fetched inputs.
