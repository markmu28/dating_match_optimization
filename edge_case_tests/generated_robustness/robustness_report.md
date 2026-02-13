# Robustness Test Report

- Total cases: 11
- Passed: 11
- Failed: 0
- Normal cases: 6
- Extreme cases: 5

## Case Results

| Case | Category | Expected Success | Solved | Pattern OK | Result | Time(s) |
|---|---|---:|---:|---:|---:|---:|
| `normal_01_id` | normal | True | True | True | PASS | 3.53 |
| `normal_02_name_mixed` | normal | True | True | True | PASS | 3.47 |
| `normal_03_subject_name_col` | normal | True | True | True | PASS | 3.43 |
| `normal_04_pairing_odd` | normal | True | True | True | PASS | 1.51 |
| `normal_05_round1_for_round2` | normal | True | True | True | PASS | 3.51 |
| `normal_06_round2` | normal | True | True | True | PASS | 3.50 |
| `extreme_01_unknown_target` | extreme | True | True | True | PASS | 3.41 |
| `extreme_02_ambiguous_alias` | extreme | True | True | True | PASS | 3.36 |
| `extreme_03_strict_2by2_infeasible` | extreme | False | False | True | PASS | 0.41 |
| `extreme_04_pairing_diff2` | extreme | False | False | True | PASS | 0.41 |
| `extreme_05_vip_infeasible` | extreme | False | False | True | PASS | 0.41 |

## Failed Cases Details

- None