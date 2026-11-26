# Plant Care Companion

Team 3 · ECE/CSC 571

PlantCare monitors a golden pothos with a XIAO ESP32-S3, a web dashboard, and a PlantFace AMOLED display bridge. The XIAO controls live bottom watering locally.

| Start here | Contents |
| --- | --- |
| [Current PlantCare project](Updated_Project/PlantCare/README.md) | Firmware, cloud backend, dashboard, tests, and local preview |
| [Bottom-watering setup](Updated_Project/PlantCare/docs/BOTTOM_WATERING.md) | Flashing, bench checks, and approved cloud rollout |
| [PlantFace AMOLED bridge](Updated_Project/PlantCare/firmware/display/README.md) | Integration with the separate PlantFace GUI project |
| [24-hour data collection](Data_Collection/PlantCare_24Hour_Log/README.txt) | Standalone acquisition sketch and serial logger |
| [Historical evidence](Updated_Project/PlantCare/evidence/README.md) | Test logs, prototype code, and earlier setup notes |

Run build and test commands from `Updated_Project/PlantCare`. Use its `template.yaml` for AWS change-set review. It defines direct Live ingestion and keeps both SQS mappings disabled. Deployment requires separate approval.
