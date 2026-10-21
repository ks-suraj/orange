# Evaluation summary - model `anthropic/claude-haiku-5.5`

Scenarios: 12 × repeats: 3

| Metric | baseline | multi_agent |
|---|---|---|
| Diagnosis accuracy (all scenarios) | 0.833 | 0.556 |
| Accuracy - scenarios with a determinable root cause | 0.900 | 0.467 |
| Accuracy - scenarios that should be inconclusive | 0.500 | 1.000 |
| Top hypothesis correct (ignoring abstention) | 0.967 | 0.900 |
| Correct cause in top 3 | 0.967 | 0.900 |
| Conclusive on a planted decoy | 0.000 | 0.000 |
| Abstained when a cause was determinable | 0.067 | 0.500 |
| Citation validity (cited ids that exist) | 0.974 | 0.998 |
| Key evidence cited in report | 0.906 | 0.962 |
| Key evidence retrieved by tools | 0.906 | 0.962 |
| Tool calls per run | 9.389 | 30 |
| Failed tool calls per run | 0.583 | 1.389 |
| LLM calls per run | 3.861 | 29 |
| Invalid agent outputs (repair attempts) per run | 0.000 | 0.306 |
| Prompt tokens per run | 41,332 | 235,264 |
| Completion tokens per run | 4,373 | 33,604 |
| Total tokens per run | 45,705 | 268,868 |
| Total cost (USD, provider-reported) | 0.228 | 1.452 |
| Mean latency (s) | 23 | 126 |
| Median latency (s) | 22 | 127 |
| Errored runs | 0 | 0 |
| Runs with unreported usage | 0 | 0 |

## Per-scenario results

| Scenario | System | Rep | Correct | Status | Top hypothesis | Tool calls | Tokens | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| S01 | multi_agent | 1 | no | inconclusive | checkout-service / deployment_regression | 30 | 311925 | 156.2 |
| S01 | multi_agent | 2 | no | inconclusive | checkout-service / deployment_regression | 30 | 310295 | 139.4 |
| S01 | multi_agent | 3 | no | inconclusive | checkout-service / deployment_regression | 30 | 246877 | 119.1 |
| S01 | baseline | 1 | yes | conclusive | checkout-service / deployment_regression | 9 | 38309 | 20.6 |
| S01 | baseline | 2 | yes | conclusive | checkout-service / deployment_regression | 8 | 48182 | 19.8 |
| S01 | baseline | 3 | yes | conclusive | checkout-service / deployment_regression | 8 | 37943 | 21.1 |
| S02 | multi_agent | 1 | yes | conclusive | payment-service / config_error | 30 | 309871 | 153.0 |
| S02 | multi_agent | 2 | yes | conclusive | payment-service / config_error | 30 | 288793 | 125.9 |
| S02 | multi_agent | 3 | no | inconclusive | payment-service / config_error | 30 | 309608 | 146.9 |
| S02 | baseline | 1 | yes | conclusive | payment-service / config_error | 8 | 39631 | 22.6 |
| S02 | baseline | 2 | yes | conclusive | payment-service / config_error | 8 | 39013 | 21.2 |
| S02 | baseline | 3 | yes | conclusive | payment-service / config_error | 7 | 33074 | 18.6 |
| S03 | multi_agent | 1 | no | inconclusive | notification-worker / resource_exhaustion | 30 | 335858 | 163.0 |
| S03 | multi_agent | 2 | yes | conclusive | notification-worker / resource_exhaustion | 26 | 211099 | 107.0 |
| S03 | multi_agent | 3 | no | inconclusive | notification-worker / resource_exhaustion | 30 | 305625 | 167.6 |
| S03 | baseline | 1 | yes | conclusive | notification-worker / deployment_regression | 11 | 62283 | 31.6 |
| S03 | baseline | 2 | yes | conclusive | notification-worker / deployment_regression | 7 | 32106 | 20.1 |
| S03 | baseline | 3 | yes | conclusive | notification-worker / deployment_regression | 10 | 45186 | 27.8 |
| S04 | multi_agent | 1 | yes | conclusive | payment-provider / dependency_failure | 30 | 304466 | 123.8 |
| S04 | multi_agent | 2 | no | conclusive | payment-service / dependency_failure | 30 | 329017 | 127.7 |
| S04 | multi_agent | 3 | no | inconclusive | payment-service / dependency_failure | 30 | 326925 | 122.2 |
| S04 | baseline | 1 | yes | conclusive | payment-provider / dependency_failure | 12 | 80185 | 26.1 |
| S04 | baseline | 2 | yes | conclusive | payment-provider / dependency_failure | 13 | 60735 | 23.8 |
| S04 | baseline | 3 | yes | conclusive | payment-provider / dependency_failure | 12 | 60743 | 24.5 |
| S05 | multi_agent | 1 | yes | conclusive | auth-service / certificate_expiry | 29 | 269244 | 114.7 |
| S05 | multi_agent | 2 | yes | conclusive | auth-service / certificate_expiry | 30 | 311731 | 148.0 |
| S05 | multi_agent | 3 | yes | conclusive | auth-service / certificate_expiry | 30 | 290878 | 127.4 |
| S05 | baseline | 1 | yes | conclusive | auth-service / certificate_expiry | 8 | 33692 | 20.2 |
| S05 | baseline | 2 | yes | conclusive | auth-service / certificate_expiry | 9 | 45608 | 21.2 |
| S05 | baseline | 3 | yes | conclusive | auth-service / certificate_expiry | 8 | 32217 | 19.5 |
| S06 | multi_agent | 1 | yes | conclusive | inventory-db / infrastructure_failure | 30 | 279217 | 105.2 |
| S06 | multi_agent | 2 | no | inconclusive | inventory-db / infrastructure_failure | 30 | 260273 | 96.1 |
| S06 | multi_agent | 3 | no | inconclusive | inventory-db / infrastructure_failure | 30 | 303816 | 139.9 |
| S06 | baseline | 1 | no | conclusive | inventory-db / dependency_failure | 11 | 51053 | 27.0 |
| S06 | baseline | 2 | yes | conclusive | inventory-db / infrastructure_failure | 12 | 50491 | 25.9 |
| S06 | baseline | 3 | yes | conclusive | inventory-db / infrastructure_failure | 10 | 49258 | 22.8 |
| S07 | multi_agent | 1 | no | inconclusive | checkout-service / traffic_surge | 30 | 325289 | 148.7 |
| S07 | multi_agent | 2 | yes | conclusive | checkout-service / traffic_surge | 30 | 314246 | 162.3 |
| S07 | multi_agent | 3 | yes | conclusive | checkout-service / traffic_surge | 30 | 256558 | 111.1 |
| S07 | baseline | 1 | yes | conclusive | checkout-service / traffic_surge | 9 | 54558 | 23.2 |
| S07 | baseline | 2 | yes | conclusive | checkout-service / traffic_surge | 10 | 55724 | 21.6 |
| S07 | baseline | 3 | yes | conclusive | checkout-service / traffic_surge | 10 | 55816 | 23.8 |
| S08 | multi_agent | 1 | no | inconclusive | payment-service / deployment_regression | 30 | 188243 | 91.7 |
| S08 | multi_agent | 2 | no | inconclusive | payment-service / deployment_regression | 30 | 188646 | 94.5 |
| S08 | multi_agent | 3 | no | inconclusive | payment-service / deployment_regression | 30 | 195395 | 91.5 |
| S08 | baseline | 1 | yes | conclusive | payment-service / deployment_regression | 10 | 53679 | 22.1 |
| S08 | baseline | 2 | no | inconclusive | payment-service / deployment_regression | 9 | 39766 | 19.5 |
| S08 | baseline | 3 | no | inconclusive | payment-service / deployment_regression | 9 | 40876 | 21.6 |
| S09 | multi_agent | 1 | no | inconclusive | inventory-service / config_error | 30 | 283199 | 129.9 |
| S09 | multi_agent | 2 | no | inconclusive | inventory-service / deployment_regression | 30 | 226000 | 93.7 |
| S09 | multi_agent | 3 | yes | conclusive | inventory-service / config_error | 30 | 299286 | 149.5 |
| S09 | baseline | 1 | yes | conclusive | inventory-service / config_error | 8 | 30202 | 20.9 |
| S09 | baseline | 2 | yes | conclusive | inventory-service / config_error | 10 | 44457 | 24.8 |
| S09 | baseline | 3 | yes | conclusive | inventory-service / config_error | 9 | 47448 | 26.4 |
| S10 | multi_agent | 1 | yes | inconclusive | search-service / dependency_failure | 28 | 170311 | 95.9 |
| S10 | multi_agent | 2 | yes | inconclusive | search-service / dependency_failure | 30 | 230424 | 129.3 |
| S10 | multi_agent | 3 | yes | inconclusive | search-service / dependency_failure | 29 | 198220 | 107.7 |
| S10 | baseline | 1 | yes | inconclusive | search-service / dependency_failure | 10 | 47428 | 24.1 |
| S10 | baseline | 2 | yes | inconclusive | search-index / resource_exhaustion | 10 | 45593 | 23.1 |
| S10 | baseline | 3 | yes | inconclusive | search-index / dependency_failure | 13 | 57892 | 27.7 |
| S11 | multi_agent | 1 | yes | conclusive | payments-db / resource_exhaustion | 30 | 281776 | 138.8 |
| S11 | multi_agent | 2 | yes | conclusive | payments-db / resource_exhaustion | 30 | 266387 | 126.4 |
| S11 | multi_agent | 3 | yes | conclusive | payments-db / resource_exhaustion | 30 | 257100 | 121.2 |
| S11 | baseline | 1 | yes | conclusive | payments-db / resource_exhaustion | 8 | 34856 | 21.6 |
| S11 | baseline | 2 | yes | conclusive | payments-db / resource_exhaustion | 10 | 51515 | 24.4 |
| S11 | baseline | 3 | yes | conclusive | payments-db / resource_exhaustion | 9 | 46892 | 23.0 |
| S12 | multi_agent | 1 | yes | inconclusive | api-gateway / config_error | 30 | 193386 | 96.6 |
| S12 | multi_agent | 2 | yes | inconclusive | api-gateway / config_error | 30 | 246123 | 138.8 |
| S12 | multi_agent | 3 | yes | inconclusive | api-gateway / config_error | 30 | 253126 | 137.8 |
| S12 | baseline | 1 | no | conclusive | api-gateway / config_error | 8 | 30256 | 19.4 |
| S12 | baseline | 2 | no | conclusive | api-gateway / config_error | 7 | 28457 | 19.4 |
| S12 | baseline | 3 | no | conclusive | api-gateway / config_error | 8 | 40260 | 21.9 |
