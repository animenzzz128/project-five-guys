# Similar colleges data

The nationwide import joins institutions by federal UNITID. The November 2026
institution snapshot contains 2,462 schools. These are the seven inputs for
issue #16 and their non-missing counts in that release.

| Institution field | Meaning | Schools reporting |
| --- | --- | ---: |
| `enrollment_undergrad` | Undergraduate enrollment | 2,441 |
| `cost_attendance` | Cost of attendance, dollars | 2,253 |
| `admission_rate` | Admissions fraction | 1,704 |
| `completion_rate_150` | Completion within 150% of normal time, fraction | 2,256 |
| `median_earnings_10yr` | Median earnings ten years after entry, dollars | 2,260 |
| `ownership` | Public, private nonprofit, or private for-profit | 2,462 |
| `region` | Federal Scorecard REGION category | 2,462 |

The preparation script copies REGION from the federal institution ZIP in the
[College Scorecard release](https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution_11022026.zip).
Use region and ownership as categories. Region codes 1–8 identify geographic
regions, 0 identifies US service schools, and 9 identifies outlying areas.
Missing values import as SQL NULL. Exactly 1,550 institutions report all seven
fields in this release. Schools with partial data can still be compared on their
shared reported features. Numerical zero is a valid reported value.

After migrating, run `python manage.py import_scorecard` to populate the region
on existing institution rows. Old and demo records without a sourced region can
keep NULL. The recommendation implementation still needs to normalize numeric
features, persist vectors during import, handle missing features, and return up
to ten schools with reasons based on the data. The deployment owner coordinates
the vector extension on CI and both Neon environments.
