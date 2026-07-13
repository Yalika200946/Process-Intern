# CPHT Analysis Pipeline — Orientation Guide

**อ่านไฟล์นี้ก่อนไฟล์อื่น** — สรุปว่าทั้งโปรเจกต์มีอะไรบ้าง เรียงลำดับยังไง หน้าไหนแสดงอะไร และอันไหนควรยุบ/เอาออก
เพื่อให้ตามงานที่ทำไปแล้วทัน ไม่ต้องไล่เปิดทีละไฟล์ 24 notebook + 15 script เอง

อ้างอิงละเอียดเพิ่มเติม: `notebooks/METHODOLOGY.md` (ระเบียบวิธี+ข้อค้นพบแบบเต็ม), `pipeline/run_all.py` (ผังรันจริง).

---

## 0. วิธีรันทั้งหมด

```
python pipeline/run_all.py                # รันใหม่ทั้งหมดด้วยข้อมูลปัจจุบัน
python pipeline/run_all.py --input new.xlsx  # เปลี่ยนไฟล์ raw ก่อนรัน
python pipeline/run_all.py --only 6c       # รันเฉพาะ terminal exporter (เร็ว, ใช้ตอนแก้ post-processing)
python pipeline/run_all.py --from 2a       # รันต่อจาก 2a (ใช้ตอนแก้อะไรกลางทาง ไม่อยากรันตั้งแต่ต้น)
```

`pipeline/run_all.py` คือผังรันจริง (ground truth) — `CHAIN` = 13 notebook หลัก, ตามด้วย hook คำนวณ fouling rate,
แล้วตามด้วย `POST` = 14 script/notebook ปิดท้าย ทุกอย่าง backup อัตโนมัติก่อนรันที่ `Data/backup_<timestamp>/`.

---

## 1. ลำดับการวิเคราะห์ที่ควรตามอ่าน (เรียงเป็นเรื่องราวเดียว)

จัดกลุ่มเป็น 7 stage ตามลำดับที่ควรทำความเข้าใจ (ไม่ใช่ลำดับรันเป๊ะ ๆ แต่ใกล้เคียงมาก — ต่างจากลำดับรันจริงแค่การจัดหมวด):

**เตรียมข้อมูล → คำนวณ feature/fouling → จัดอันดับความสำคัญ → พยากรณ์ → โมเดล CIT (3 มุมมองคู่ขนาน) → เศรษฐศาสตร์/ข้อจำกัดหน้างาน → แผนล้างรวม**

| # | ไฟล์ | Stage | ทำอะไร (ภาษาคน) | Output หลัก | เปิดดูแล้วเจออะไร |
|---|---|---|---|---|---|
| 1 | `notebooks/1_cleaning_data_process.ipynb` | เตรียมข้อมูล | โหลด raw process Excel (95 tag) + crude assay ที่ profile ไว้แล้ว, ตัดช่วง TAM/shutdown ออก, เติมค่าที่ขาด, รวมเป็นตารางเดียว | `Process_information_cleaned.csv`, `Process_information_with_crude.csv` | กราฟ timeline ก่อน/หลังตัด TAM, สรุป missing data |
| 2 | `notebooks/2_Feature_calculation.ipynb` | Feature/fouling | คำนวณ Q (duty) ต่อ HX ด้วย Watson-Nelson Cp/Rackett density, LMTD/F/UA, U_relative, Rf, furnace duty — และ fouling-rate แบบหยาบครั้งแรก (**ถูกเขียนทับด้วย #3.5 ด้านล่าง อย่าใช้เลขจากตรงนี้**) | `Feature_calculated.csv` | กราฟ U_relative sawtooth ต่อ HX, ตาราง fouling rate (ชุดที่ยังไม่ robust) |
| 3 | `notebooks/2a_operating_state_classification.ipynb` | Feature/fouling | หาว่าวันไหน shell ไหนกำลังทำงานจริง (E113A↔E112C สลับ, E101EF↔E101G spare) กันข้อมูลปนกันข้าม HX | `Operating_State.csv` | ตาราง state ต่อวันต่อ HX (NORMAL/SUBSTITUTE_ACTIVE/OFF/...) |
| 3.5 | `pipeline/compute_fouling_rate.py` *(ไม่ใช่ notebook, รันอัตโนมัติทันทีหลัง #3)* | Feature/fouling | คำนวณ fouling rate **แบบ robust ที่ถูกต้อง** ต่อรอบ — กรอง in-service state, ตัด outlier (winsorize), ใช้ Theil-Sen แทน OLS, cross-check ด้วย Rf, เช็ค physical constraint (slope ต้องติดลบ) แล้ว**เขียนทับ**ผลจาก #2 | `Fouling_Rate_By_Run.csv` (ทับของเดิม) | พิมพ์สรุป reliable/flagged runs — **นี่คือ fouling rate ตัวจริงที่ทุกอย่างต้องใช้** |
| 4 | `notebooks/2b_Q_duty_and_fouling.ipynb` | จัดอันดับ | คำนวณ Q duty ต่อ HX ใหม่ (กรองด้วย Operating_State), normalize ด้วย charge รวม, จัดอันดับตาม fouling rate/Q ที่หายไป | `Feature_Q.csv`, `Fouling_Rate_Ranking.csv` | กราฟ Q_norm ranking |
| 5 | `notebooks/2c_Q_CIT_relationship.ipynb` | จัดอันดับ | วัดว่า Q ของแต่ละ HX มีผลต่อ CIT จริงแค่ไหน (correlation + partial correlation + slope) | `Q_CIT_Sensitivity.csv` | ตาราง CIT sensitivity ต่อ HX |
| 6 | `notebooks/3a_fouling_rate_forecast.ipynb` | พยากรณ์ | โมเดล clean-baseline (fit ช่วง 30 วันแรกหลังล้าง) แล้ววัดช่องว่างทำนาย-จริงเป็นสัญญาณ fouling ที่ถี่กว่ารายรอบ | `Q_Deviation_Signal.csv` | กราฟ predicted vs actual Q (เส้นที่เห็นในแดชบอร์ดแท็บ "HX รายตัว") |
| 7 | `notebooks/3b_time_to_clean_prediction.ipynb` | พยากรณ์ | แปลงสัญญาณจาก #6 เป็น "เหลืออีกกี่วันต้องล้าง" โดยใช้ threshold จากประวัติจริงต่อ HX | `Time_To_Clean_Prediction.csv` | ตาราง days-to-clean ต่อ HX |
| 8 | `notebooks/2d_cleaning_priority_ranking.ipynb` | จัดอันดับ | รวม #4 (fouling/Q shortfall) + #5 (CIT sensitivity) + coking-risk เป็นคะแนนจัดอันดับเดียว (rank-percentile, ไม่ใช้ min-max) — **นี่คือ ranking ตัวจริงที่ระบบอื่นใช้ต่อ** | `Cleaning_Priority_Ranking.csv`, `Engineering_Priority_Score.csv` | ตารางจัดอันดับ E113A/E109AB/... พร้อม probability×consequence÷effort |
| 9 | `notebooks/5_HX_fouling_CIT_ranking.ipynb` | โมเดล CIT | Notebook สำรวจรุ่นแรก (ใหญ่กว่า) — สร้าง feature matrix สำหรับโมเดล CIT และเทรน RF/XGB/LSTM ตัวแรก **หน้าที่จริงคือ "สร้างวัตถุดิบให้ #10-12" ไม่ใช่ ranking ที่ใช้งานจริง** (ranking ที่ใช้จริงคือ #8) | `hx_Q_cleaning_priority.csv` | ranking เวอร์ชันเก่า (เก็บไว้เพราะ #10-12 อ่านไฟล์นี้ต่อ) |
| 10 | `notebooks/6a_model_benchmark_xgb_lstm_rf.ipynb` | โมเดล CIT (มุมพยากรณ์) | เทียบ XGB/RF/LSTM กับ **persistence baseline** (CIT วันนี้=เมื่อวาน) ด้วย walk-forward CV — **ข้อค้นพบหลัก: persistence ชนะ (R²≈0.80), ML แพ้ทุกตัว** | `Model_Comparison_Metrics.csv` | ตาราง CV R²/RMSE เทียบ baseline |
| 11 | `notebooks/6b_shap_importance_ranking.ipynb` | โมเดล CIT (มุม attribution) | เอาโมเดลจาก #10 มาหา SHAP importance — ย้ำว่าเป็น **ความสัมพันธ์ ไม่ใช่การพยากรณ์** (เพราะ #10 บอกแล้วว่าโมเดลแพ้ baseline) | `hx_Q_cleaning_priority_v2.csv` | กราฟ SHAP bar ranking HX ที่มีผลต่อ CIT มากสุด |
| 12 | `notebooks/6d_clean_baseline_delta_cit.ipynb` | โมเดล CIT (มุม clean-baseline) | วิธีที่ 3: เทรนเฉพาะช่วงหลัง TAM ที่ยืนยันว่าสะอาดจริง (2024-06-14) แล้ววัด Δ CIT จากจุดนั้น — cross-check วิธี #10/#11 | `clean_baseline_sandbox.json` (ใช้จริง), `Delta_CIT_*.csv` (ไม่มีใครอ่านต่อ) | กราฟ Δ CIT ต่อ HX |
| 13 | `notebooks/6c_six_month_forecast_and_dashboard_export.ipynb` | Export | รวบผลจาก #7/#11/#10 พยากรณ์ล่วงหน้า 182 วัน แล้ว export JSON หลักเกือบทั้งหมดให้แดชบอร์ด | `forecast_6mo.json`, `hx_ranking.json`, `cleaning_recommendations.json` | เป็น export notebook ไม่มีอะไรให้ดูเอง |
| 14 | `pipeline/gen_honest_metrics.py` | Export (แก้ #13) | เขียนทับ `model_metrics.json` ที่ #13 สร้างแบบ misleading (split เดียว R²≈0.82) ด้วยตัวเลข walk-forward CV ที่ซื่อสัตย์จาก #10 | `model_metrics.json` (ทับ) | — |
| 15 | `notebooks/add_forecast_intervals.py` | Export | เติมแถบความเชื่อมั่น (√t growth) ให้กราฟพยากรณ์ 6 เดือน | `forecast_6mo.json` (เติม) | — |
| 16 | `notebooks/build_dashboard_topology.py` | Export | สร้าง P&ID/topology JSON + ค่าคงที่เตา F101 | `pfd_topology.json` | — |
| 17 | `pipeline/phm_analysis.py` | Export | RUL (Monte-Carlo P10/50/90), Weibull reliability, SHAP degradation driver (associative เท่านั้น) | `rul.json`, `reliability.json`, `drivers.json`, `propagation_models.json` | ป้อนแท็บ "พยากรณ์ & ความเสี่ยง" |
| 18 | `pipeline/export_hx_timeseries.py` | Export | Time-series ต่อ HX สำหรับแท็บ "HX รายตัว" | `hx_timeseries.json` | — |
| 19 | `pipeline/export_end_of_run.py` | Export | คำนวณ "ใกล้เกณฑ์ล้างแค่ไหน" ต่อ HX พร้อม guard กัน rate ค้างจากรอบเก่า (`rate_source`) | `end_of_run.json` | — |
| 20 | `pipeline/export_cleaning_history.py` | เศรษฐศาสตร์/ข้อจำกัด | ตรวจสอบทุกเหตุการณ์ล้าง/สลับในอดีต เทียบ CIT ที่คืนจริง vs โมเดล | `cleaning_history.json` | ตารางประวัติล้างในแท็บ "HX รายตัว" |
| 21 | `pipeline/export_economics.py` | เศรษฐศาสตร์/ข้อจำกัด | โมเดลเงินเดียว: CIT → ฿/ปี ด้วยสูตรโรงงาน, ใช้ ΔCIT วัดจริงก่อนเสมอ | `economics.json` | — |
| 22 | `notebooks/cleaning_logistics.py` | เศรษฐศาสตร์/ข้อจำกัด | จำแนกวิธีล้างต่อ HX จากไฟล์ bypass จริงของโรงงาน (full/บางส่วน/none) | `cleaning_logistics.json` | ตารางในแท็บ "แผนล้าง HX" |
| 23 | `notebooks/4_tam_deep_analysis.ipynb` | เศรษฐศาสตร์/ข้อจำกัด | วิเคราะห์ CIT เต็มช่วง 2021-2026, SOR/EOR ต่อรอบ, event-study ต่อการล้างทุกครั้ง (รันท้าย ๆ เพราะต้องใช้ output ที่แก้ไขแล้วทั้งหมด ไม่ใช่เพราะสำคัญน้อย) | `tam_analysis.json` | กราฟ CIT slide-style ในแท็บ "แผนล้าง HX" |
| 24 | `pipeline/cleaning_scheduler.py` (v1) | เศรษฐศาสตร์/ข้อจำกัด | ช่วงล้างที่เหมาะสมต่อ HX แบบอิสระ T\*=√(2C/kr), เพดาน 4 ครั้ง/ปี | `cleaning_schedule.json` | ใช้เป็น input ให้ #25/#27 (ไม่แสดงบนแดชบอร์ดตรง ๆ แล้ว) |
| 25 | `pipeline/cleaning_scheduler_network.py` (v2) | เศรษฐศาสตร์/ข้อจำกัด | จัดตารางทั้งเครือข่ายพร้อมกัน (moving-window optimizer), เทียบกับ v1 อย่างเป็นธรรม | `cleaning_schedule_v2.json` | ใช้เป็น input ให้ #27 |
| 26 | `pipeline/export_evidence.py` | เศรษฐศาสตร์/ข้อจำกัด | รวมหลักฐาน+ความเชื่อมั่นทั้งหมดไว้ที่เดียว | `evidence.json` | แท็บ "หลักฐาน & ความเชื่อมั่น" ทั้งแท็บ |
| 27 | `notebooks/8_cleaning_plan_optimization.ipynb` | **แผนล้างรวม** | รวมความคุ้มค่า+ประสิทธิภาพ+ความเป็นไปได้(bypass จริง)+ความวิกฤต เป็น**แผนเดียว**ที่แนะนำ พร้อมเทียบมูลค่าเชื้อเพลิงเตาโดยตรง (`worth_it`) | `cleaning_plan.json` | แท็บ "แผนล้าง HX" ทั้งแท็บ (ตาราง+Gantt+เหตุผล) |

**ทุกไฟล์ในตารางนี้คือ pipeline จริงที่ยังใช้งานอยู่ ไม่มีตัวไหนซ้ำซ้อนกันเปล่า ๆ** — ดูเหตุผลที่ #4/#8/#9 และ #10/#11/#12
ดูเหมือนซ้ำแต่ไม่ซ้ำ ในหัวข้อ 5 ด้านล่าง

---

## 2. แท็บแดชบอร์ด → มาจาก pipeline ขั้นไหน

| แท็บ (ลำดับปัจจุบัน) | มาจาก step # | ตอบคำถามอะไร |
|---|---|---|
| ภาพรวม & P&ID | #13, #16, #8 | ภาพรวมโรงงานตอนนี้เป็นยังไง ต้องดู HX ไหนก่อน |
| HX รายตัว | #18, #19, #20 | ข้อมูลดิบ/ประวัติของ HX ตัวที่เลือกเป็นยังไง เชื่อถือได้แค่ไหน |
| เตา & Optimization | #16, #21, #8 | fouling กระทบเตาแค่ไหน คุ้มเงินไหมถ้าเดินต่ำกว่าเกณฑ์ |
| แผนล้าง HX | #27, #22, #23 | ควรล้างอะไรเมื่อไหร่ ภายใต้ข้อจำกัดจริง คุ้มไหม |
| พยากรณ์ & ความเสี่ยง | #17 | เหลือเวลาอีกกี่วันก่อนต้องล้างแต่ละตัว อะไรขับเคลื่อน |
| โมเดล & Optimization | #14, #10 | เชื่อโมเดลได้แค่ไหน + ปุ่มสั่งรัน pipeline ใหม่ |
| หลักฐาน & ความเชื่อมั่น | #26 | อะไรวัดจริง/โมเดล/สมมติ + caveat ทั้งหมด |

> **ข้อเสนอแนะ (ยังไม่แก้):** สลับลำดับ "แผนล้าง HX" กับ "พยากรณ์ & ความเสี่ยง" — เหตุผลที่แผนล้างควรล้างอะไรก่อนมาจาก
> ข้อมูลความเสี่ยง/เวลาที่เหลือ (แท็บพยากรณ์) ดังนั้นควรดูพยากรณ์ก่อนแล้วค่อยดูแผน ไม่ใช่กลับกัน.
> ลำดับที่แนะนำ: ภาพรวม → HX รายตัว → เตา → **พยากรณ์ & ความเสี่ยง** → **แผนล้าง HX** → โมเดล → หลักฐาน.

---

## 3. Notebook ที่ไม่ได้อยู่ใน pipeline อัตโนมัติ (สำรวจ/อ้างอิงเฉยๆ)

ไม่ถูกเรียกโดย `run_all.py` — เปิดดูได้เพื่อความเข้าใจ แต่ไม่ต้องรันตามงานประจำวัน:

| Notebook | ทำอะไร | หมายเหตุ |
|---|---|---|
| `0_profiling_process_control.ipynb` | สำรวจข้อมูล raw เบื้องต้น (missing%, distribution) | ไม่มี output ที่ใครอ่านต่อ |
| `0_profilling_Crude.ipynb` | ทำความสะอาด crude assay | **output ถูกใช้จริงโดย #1** เพียงแต่ไม่ได้ถูกรันซ้ำใน `run_all.py` (สมมติว่าไฟล์นิ่งแล้ว) |
| `2_correlation.ipynb` | หา correlation ของ fouling driver ต่างๆ | ดูหัวข้อ 4 — แนะนำให้ยุบรวมกับ `2_pca` |
| `2_pca.ipynb` | PCA ลดมิติของ fouling state | ดูหัวข้อ 4 |
| `7_pipeline_diagnostic_review.ipynb` | โหลดผลทุกขั้นตอน 0→6d มาเขียนสรุป/รีวิวเป็นข้อความ | เป็นเครื่องมือรีวิว ไม่ใช่ pipeline stage |

---

## 4. ข้อเสนอยุบรวม (ยังไม่ทำ — รอคุณตัดสินใจ)

1. **ยุบ `2_correlation.ipynb` + `2_pca.ipynb` → `2_correlation_and_pca.ipynb` เดียว** — ทั้งคู่เป็น EDA ล้วนบน
   `Feature_calculated.csv` เดียวกัน ไม่มีใครอ่าน output ต่อ (มีแต่กราฟ) เคยเสนอไว้แล้วใน `docs/02_Requirement_v2_SSOT.md`.

2. **เปลี่ยนคำอธิบายบทบาทของ `5_HX_fouling_CIT_ranking.ipynb`** (ไม่ต้องแก้โค้ด แค่แก้ comment/markdown หัว notebook)
   จาก "ranking notebook" เป็น **"ตัวสร้าง feature matrix + ranking รุ่นแรกให้ #10/#11 ใช้ต่อ"** — เพราะ ranking ที่ใช้งานจริง
   ตอนนี้คือ #8 (`2d`) ไม่ใช่ #9 (`5`) ห้ามลบ/รวมกับ #8 เพราะ #10-#12 ยังอ่าน output ของ #9 อยู่.

3. **ทำไม #4/#8/#9 ไม่ซ้ำกัน:** #4 (`2b`) = สัญญาณดิบ (fouling rate/Q shortfall), #8 (`2d`) = ranking รวมที่ใช้จริง
   (ผสาน CIT sensitivity + coking risk), #9 (`5`) = แหล่ง feature matrix ให้สาย ML (#10-12) — คนละสายงานที่มาบรรจบกันที่ #27.

4. **ทำไม #10/#11/#12 ไม่ซ้ำกัน:** #10 ตอบ "โมเดลพยากรณ์ CIT ได้จริงไหม" (คำตอบ: ไม่, แพ้ persistence),
   #11 ตอบ "โมเดลนั้นให้น้ำหนัก HX ไหนบ้าง" (attribution คนละคำถามกับพยากรณ์), #12 เป็นวิธีคำนวณทางเลือกที่ 3
   (clean-baseline) ไว้ cross-check — ผลที่ใช้จริงมีแค่ `clean_baseline_sandbox.json`.

5. **ทำไม scheduler v1/v2/notebook 8 ไม่ซ้ำกัน:** v1 = คำนวณอิสระต่อ HX (อธิบายง่าย), v2 = จัดตารางทั้งเครือข่ายพร้อมกัน
   (แม่นกว่า ~14%), notebook 8 = **ชั้นรวม** ที่เอาสัญญาณจาก v1/v2 + ข้อจำกัดหน้างานจริง + ความวิกฤต มารวมเป็นแผนเดียว
   ที่แนะนำจริง — v1/v2 ยังต้องรันต่อไปเพราะ notebook 8 ใช้ผลเทียบ v1-vs-v2 เป็นส่วนหนึ่งของรายงาน.

---

## 5. ข้อเสนอเอาออก (ยังไม่ทำ — รอคุณตัดสินใจ)

### 5.1 ลบไฟล์ได้เลย (ยืนยันแล้วว่าไม่มีใครอ่านต่อ)
- `notebooks/01_case_operate_state.ipynb` — ต้นแบบ redesign ที่ค้างไว้ (`docs/02_Requirement_v2_SSOT.md` ยังเป็น DRAFT
  รอ approve) เขียนทับ**ชื่อไฟล์เดียวกัน** `Operating_State.csv` กับ #3 — เสี่ยงชนกันถ้าเผลอรัน
- `notebooks/test_output.ipynb` — สำเนาซ้ำของ `0_profiling_process_control.ipynb`
- `notebooks/scratch_fouling/` (ทั้งโฟลเดอร์) — sandbox ทดลองเก่า
- root `nul`, `scratch_12mo.csv` — ไฟล์เศษ
- `notebooks/_build_*.py`, `notebooks/_insert_*.py` — สคริปต์สร้าง notebook ครั้งเดียว ไม่ถูกเรียกจาก `run_all.py`
  (ยกเว้น `_build_cleaning_plan_notebook.py` ที่ยังใช้งานอยู่ถ้าจะแก้ notebook 8 — **เก็บตัวนี้ไว้ตัวเดียว**)

### 5.2 หยุด export ไฟล์ที่ไม่มีใครอ่าน (notebook ยังอยู่ แค่เอา cell export ออก)
- `Cleaning_Combined_Action_List.csv` (จาก #8 `2d`)
- `Delta_CIT_Signal.csv`, `Delta_CIT_Cleaning_Gain.csv` (จาก #12 `6d` — เก็บแค่ `clean_baseline_sandbox.json`)

### 5.3 โค้ดตายในแดชบอร์ด (`dashboard/index.html`)
`SchedulePanel`, `NetworkSchedulePanel`, `PlanTable` — ถูกนิยามไว้แต่ไม่ถูกเรียกใช้ใน `App()` อีกแล้ว (ถูกแทนที่ด้วย
`CleaningPlanPanel`) ลบ component 3 ตัวนี้ + การ fetch ที่หน้าเว็บได้เลย **แต่ห้ามหยุด generate `cleaning_schedule.json`/
`cleaning_schedule_v2.json`** — ไฟล์ทั้งสองยังจำเป็นสำหรับ #25/#27 (ใช้เทียบ v1-vs-v2 ภายใน notebook 8) แค่หน้าเว็บไม่ต้อง
fetch/แสดงตรง ๆ อีกแล้ว.

---

## 6. สถานะการทำตามข้อเสนอ §2/§4/§5 (อัปเดต 2026-07-12)

ทุกข้อเสนอในหัวข้อ 2, 4, 5 ด้านบน **ทำเสร็จแล้ว**:
- ลำดับแท็บสลับแล้ว (พยากรณ์&ความเสี่ยง มาก่อนแผนล้าง HX)
- ยุบ `2_correlation.ipynb`+`2_pca.ipynb` → `2_correlation_and_pca.ipynb` แล้ว (รันผ่าน, ไม่มี error)
- แก้ header markdown ของ `5_HX_fouling_CIT_ranking.ipynb` ให้บอกบทบาทจริงชัดเจนแล้ว
- ไฟล์ตาย/สคริปต์ scaffolding ทั้งหมดใน §5.1 ย้ายไป `notebooks/_archive_2026-07-12/` แล้ว (ไม่ได้ลบถาวร เผื่อต้องใช้อ้างอิง)
- เอา export `Cleaning_Combined_Action_List.csv` (2d) และ `Delta_CIT_Signal.csv`/`Delta_CIT_Cleaning_Gain.csv` (6d) ออกแล้ว
- ลบ `SchedulePanel`/`NetworkSchedulePanel`/`PlanTable` + fetch ที่ไม่ใช้แล้วออกจากแดชบอร์ดแล้ว

ตารางในหัวข้อ 1 ด้านบนยังตรงกับโครงสร้างปัจจุบัน (ไม่มีขั้นตอนไหนถูกลบ เปลี่ยนแค่ไฟล์ #4 ในหัวข้อ 4 ที่ตอนนี้ชื่อ
`2_correlation_and_pca.ipynb` แทน).

---

## 7. เรื่องที่แก้ไปแล้ว — อย่าหยิบมาแก้ซ้ำ

- **Fouling rate เก่าผิดฟิสิกส์ (slope เป็นบวก)** → แก้แล้วด้วย `pipeline/compute_fouling_rate.py` (Theil-Sen + robust) ดู §11 ใน METHODOLOGY
- **ลิสต์ bypass เขียนมือขัดกับไฟล์จริงของโรงงาน** → แก้แล้ว ใช้ `bypass_config.py` เป็นแหล่งเดียว ดู §12
- **`model_metrics.json` จาก #13 เป็นตัวเลข misleading (split เดียว)** → ถูกเขียนทับด้วย `gen_honest_metrics.py` เสมอ (ตั้งใจ)
- **`worsening` metric ดูเหมือน bug** → ไม่ใช่ ตั้งใจให้เป็นคนละแกนกับ raw rate (ดู METHODOLOGY §3D)
- **ΔCIT จากโมเดล over-estimate ~3× vs วัดจริง** → รู้แล้ว ตั้งใจให้ใช้ค่าวัดจริงก่อนเสมอ (measured-first)
- **ค่าล้าง HX / เพดานความถี่ 4 ครั้ง-ต่อปี / E112C rate ค้าง** → แก้ไปแล้วทั้งหมดในรอบก่อนหน้า (ดู METHODOLOGY §10)

---

*เอกสารนี้สร้างจากการสำรวจโค้ดจริง 2026-07-12 — ถ้าโครงสร้าง pipeline เปลี่ยนหลังจากนี้ ให้ปรับไฟล์นี้ตามไปด้วย
(ไม่งั้นจะเก่าเหมือน METHODOLOGY.md §3 ที่เคยเจอปัญหานี้มาก่อน).*
