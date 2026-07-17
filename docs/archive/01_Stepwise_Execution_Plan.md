# Stepwise Execution Plan — รายละเอียดการทำงานทีละขั้น

อ้างอิงจาก [00_Requirement_and_Redesign_Plan.md](00_Requirement_and_Redesign_Plan.md) — เอกสารนี้ขยายหัวข้อ 6-8 ของแผนหลัก ให้เป็น checklist ที่ลงมือทำได้จริงทีละ Step พร้อม**ลำดับการทำงานที่แก้ไขใหม่ตาม dependency จริง** (ลำดับเดิมในเอกสารหลักยังไม่ตรง — ดูหัวข้อ 0 ก่อน)

---

## 0. แก้ลำดับการทำงาน — พบ dependency ที่ตกไปในแผนแรก

แผนเดิมเสนอลำดับ `1 → 3 → 6 → 7 → 9` แต่จริงๆ **Step 6 (ranking) ต้องใช้ SHAP importance จาก Step 8 ซึ่งต้องรอโมเดลจาก Step 7 ก่อน** และ **Step 9 (what-if) ต้องใช้ทั้ง Step 4 + 6 + 7** ดังนั้น graph ที่ถูกต้องคือ:

```
Step 0 (clean data)
   └─ Step 1 (case-operate label)
        └─ Step 2 (Q features, single source)
             ├─ Step 3 (fouling phase + rate)  ──┐
             │      └─ Step 4 (time-to-clean)     │
             ├─ Step 5 (correlation/PCA, exploratory, ทำคู่ขนานได้)
             └─ Step 7 (train CIT model: RF/XGB/LSTM, train/val/test)
                    └─ Step 8 (SHAP importance)   │
                                                    ▼
                              Step 6 (ranking รวมคะแนน: fouling rate × SHAP × safety × effort)
                                                    │
                              Step 9 (12-month forecast + what-if CIT target) ◄── ใช้ Step 4 + 6 + 7
```

**ลำดับลงมือทำจริง (revised):**
`0/0b → 1 → 2 → 3 → {5, 7} → {4, 8} → 6 → 9`

ทำ Step 3 กับ Step 7 "คู่ขนานกันได้" หลัง Step 2 เสร็จ (ไม่ต้องรอกัน) เพราะ Step 3 ใช้ Q_norm ต่อ HX เฉยๆ ส่วน Step 7 ใช้ feature matrix รวม 64 features — คนละ input ไม่ block กัน

---

## Step 0 / 0b — Data Ingestion & Cleaning
**Objective:** มีไฟล์ input สะอาด 1 ชุดที่ทุก Step ถัดไปใช้ร่วมกัน (ของเดิมถูกต้องแล้ว งานนี้คือ "รวมไฟล์" ไม่ใช่เขียนใหม่)

**สิ่งที่ต้องทำ:** *(หมายเหตุ Phase 1: `00_data_prep_crude_assay.ipynb`/`00_data_prep_process_control.ipynb` ถูกเปลี่ยนชื่อเป็น
`_eda_crude_assay.ipynb`/`_eda_process_control.ipynb` แล้ว — ข้อเสนอ merge ด้านล่างนี้ยังไม่ได้ทำ, เป็นข้อเสนออนาคตแยกจาก
`docs/MIGRATION_PLAN.md`)*
1. รวม `_eda_crude_assay.ipynb` (crude property cleaning) + `01_data_cleaning.ipynb` (TAM removal, outlier fix, merge crude) → ไฟล์เดียว `00_data_ingestion_and_cleaning.ipynb`
2. เก็บ logic เดิมทั้งหมดไว้ (thresholds, IQR outlier, chain-consistency check) — **ไม่แก้สมการ**
3. `_eda_process_control.ipynb` → เก็บแยกเป็น `00b_process_profiling.ipynb` (EDA อย่างเดียว, ไม่มีไฟล์ output ที่ step อื่นพึ่ง)
4. Output ที่ต้องคงชื่อเดิมไว้ (มี notebook อื่นอ้างอิงอยู่): `Process_information_with_crude.csv`

**Validation checklist:**
- [ ] จำนวนแถวหลัง merge ตรงกับของเดิม (836 วัน)
- [ ] ไม่มี TAM period หลุดเข้ามา (`is_shutdown` sum เท่าเดิม)
- [ ] Crude property coverage ยังเป็น forward-fill ต่อ batch เหมือนเดิม

**Effort: S (house-keeping, ไม่มีการคำนวณใหม่)**

---

## Step 1 — Case-Operate / Operating-State Resolution
**Objective:** ได้ 1 ตาราง state ต่อวันต่อ HX ที่ระบุ case-operate ตรงกับ 3 กรณีจริงที่ระบุไว้ในหัวข้อ 2 ของแผนหลัก

**สิ่งที่ต้องทำ (ต่อจาก `2a` เดิม):**
1. คงตรรกะเดิมทั้งหมด (E101EF↔E101G mass-balance, E113A↔E112C threshold 150°C)
2. **เพิ่มคอลัมน์ใหม่** `residue_chain_case` ต่อวัน โดย derive จาก state ของ E113A/E112C/E112AB:
   - `NORMAL` = E113A active, E112C idle, ไม่มี bypass
   - `E113A_CLEANING` = E113A idle, E112C active (substitute)
   - `E112C_CLEANING` = E112C idle, E113A active (ปกติ แยกจาก NORMAL ด้วย flag ว่า "รู้ว่ากำลังมีการ clean E112C อยู่" ถ้ามี maintenance log แนบมา ถ้าไม่มี log ให้ปล่อยเป็น NORMAL เพราะดูจากข้อมูล process ล้วนแยกไม่ออกจาก NORMAL — **ต้องขอ maintenance log จากผู้ใช้เพื่อแยกกรณีนี้ให้ชัด**)
   - `E112AB_BYPASS` = ใช้ `E112AB_BYPASS_DT_THRESH` เดิม (ยังไม่เคย trigger ในข้อมูล — เตรียม logic รอ)
3. ทำ Gantt-style timeline plot ต่อ HX เพื่อ QA ด้วยตา (เช็คว่าไม่มีวันที่ E113A และ E112C off พร้อมกันทั้งคู่ ซึ่งจะเป็น error เพราะไม่มีอะไรวิ่งในสาย residue เลย)
4. Export `Operating_State.csv` (คงชื่อเดิม เพิ่มคอลัมน์ใหม่ ไม่ลบของเก่า เพราะ notebook อื่นอ้าง path เดิม)

**Decision point ที่ต้องถามผู้ใช้:**
- มี maintenance/cleaning log ย้อนหลังไหม (วันที่ clean จริงของแต่ละ HX) — ถ้ามีจะช่วยแยก `E112C_CLEANING` จาก `NORMAL` ได้แม่นขึ้นมาก และยังใช้ validate campaign boundary ใน Step 3 ได้ด้วย

**Validation checklist:**
- [ ] ไม่มีวันที่ residue chain ทั้งคู่ (E113A, E112C) off พร้อมกัน
- [ ] จำนวนวัน `E113A_CLEANING` + `NORMAL` (สำหรับ E113A) รวมกันเท่ากับ total days
- [ ] `E112AB_BYPASS` = 0 วัน ยืนยันตามข้อมูลปัจจุบัน (ตรงกับที่พบใน `2a` เดิม)

**Effort: S–M**

---

## Step 2 — Engineering Feature Calculation (Q, single source)
**Objective:** มีจุดคำนวณ `Q` เพียงจุดเดียวในทั้งระบบ (ปัจจุบันสมการเหมือนกันระหว่าง `2b`/`5` อยู่แล้ว แต่เขียนซ้ำคนละไฟล์ — เสี่ยงหลุดไม่ sync กันในอนาคต)

**สิ่งที่ต้องทำ:**
1. ย้ายสมการ Q (Watson-Nelson Cp, Rackett density, `Q_norm`) จาก `2b`/`5` เข้าไปเป็น**ฟังก์ชันเดียวใน `cpht_features.py`** เช่น `compute_Q(flow, T_in, T_out, SG) -> Q_kW`
2. ทุก notebook ถัดไป (`3`, `5→7`) เรียกฟังก์ชันนี้ ไม่ copy-paste สมการอีก
3. รวม `02_feature_engineering.ipynb` เข้าเป็น `02_engineering_features_Q.ipynb` ที่ output `Feature_Q.csv` (Q_norm ต่อ HX ต่อวัน) — ใช้ operating mask จาก Step 1 (`VALID_STATES`, `MIN_DT_COLD=3`, `MIN_FLOW_FRAC=0.10`)

**Validation checklist:**
- [ ] ค่า Q ที่ได้จากฟังก์ชันใหม่ตรงกับค่าเดิมใน `Feature_Q.csv` เดิม (diff < 0.1%) — เป็น regression test ว่าไม่ได้เปลี่ยนสมการโดยไม่ตั้งใจ

**Effort: S (refactor, ไม่เปลี่ยนตัวเลข)**

---

## Step 3 — Fouling Phase Segmentation & Rate Estimation ⚠️ งานที่ต้องออกแบบใหม่มากที่สุด
**Objective:** แทนที่ `2b` (linear-only) + `3a` (ML-baseline) ด้วยกรอบเดียวตาม Initiation/After-initiation phase

**สิ่งที่ต้องทำ (ตามลำดับ):**
1. **Campaign detection** — รวม logic เดิม 3 สัญญาณ (TAM date, state transition จาก Step 1, Q-jump ≥15% median) ให้เป็นฟังก์ชันเดียวใช้ร่วมกันทุก HX (ของเดิมมี 2 เวอร์ชันต่างกันใน `2b` กับ `5` — เลือกเวอร์ชันที่ dedup ดีกว่าและรวมเป็นหนึ่ง)
2. **Initiation window** — สำหรับทุก campaign ที่ยาว ≥30 วัน ตัดวันที่ 0–~21 (train) และ 22–30 (held-out) เป็น "initiation data" ตาม design เดิมของ `3a`
3. **Clean-state baseline model** — pool ข้อมูล initiation window ของทุก HX/campaign, fit GradientBoosting (ของเดิมได้ test R²=0.91 ดีอยู่แล้ว) บน feature: `cold_flow, cold_in, chain_position, hot_end, group` → เก็บโมเดลนี้ (`joblib`)
4. **Deviation signal** = `predicted_baseline_Q − actual_Q` ตลอดทั้ง after-initiation phase ของทุก HX (แทนที่ percentile-baseline วิธีเก่าของ `2b`)
5. **Rate fitting ต่อ campaign** — fit 2 โมเดลแข่งกัน แล้วเลือกด้วย AIC (หรือ adjusted-R² ถ้า n น้อย):
   - Linear: `deviation(t) = a + b·t`
   - Kern-Seaton: `deviation(t) = D∞(1 − e^{−t/τ})`
   - เก็บ `rate_type` (linear/asymptotic), พารามิเตอร์, R², n_points, confidence (นับจาก n cleaning events ที่มีจริงของ HX นั้น)
6. **Sanity check plot** ต่อ HX: deviation ต้อง reset กลับใกล้ 0 หลัง clean event ทุกครั้ง (เกณฑ์ QA แบบเดียวกับที่ `3a` เคยใช้)
7. Export `Fouling_Rate_Estimate.csv` (คอลัมน์: HX, campaign_id, start, end, phase, rate_type, rate_value, R2, confidence)

**Decision point:**
- ถ้า Kern-Seaton fit ไม่ converge ดี (τ ไม่ stable) ในบาง campaign สั้นเกินไป (<20 จุด) ให้ fallback เป็น linear เสมอ — ตั้ง threshold ขั้นต่ำของจำนวนจุดข้อมูลไว้ล่วงหน้า (แนะนำ ≥15 จุด จึงลอง fit asymptotic)

**Validation checklist:**
- [ ] ทุก HX มี ≥1 campaign ที่ fit สำเร็จ
- [ ] Deviation reset ~0 หลัง clean event ที่รู้แน่ชัด (cross-check กับ maintenance log ถ้ามีจาก Step 1)
- [ ] เทียบ rate ที่ได้กับของเดิมจาก `2b`/`3a` — ทิศทาง (เร็ว/ช้า) ของแต่ละ HX ต้องสอดคล้องกัน แม้ตัวเลขจะเปลี่ยน

**Effort: L (เป็นจุดที่ใช้เวลามากที่สุดในทั้งแผน)**

---

## Step 4 — Time-to-Clean Prediction
**Objective:** แปลง rate จาก Step 3 เป็นวันที่ควร clean ต่อ HX (logic เดิมของ `3b` ใช้ได้ เปลี่ยนแค่ input source)

**สิ่งที่ต้องทำ:**
1. ใช้ `rate_value`/`rate_type` จาก `Fouling_Rate_Estimate.csv` (Step 3) แทน `Q_Deviation_Signal.csv` เดิม
2. threshold ต่อ HX: ใช้ median deviation ณ วันก่อน clean จริง (ตามของเดิม) — ถ้า HX มี event น้อย (<3) ใช้ group median ของ CPHT-1/CPHT-2 เป็น fallback (คงไว้ตามเดิม)
3. **แก้ NEXT_TAM_DATE placeholder** เป็นวันที่จริง (รอคำตอบจากผู้ใช้ — ดู Decision point ในเอกสารหลัก หัวข้อ 7.2)
4. Export `Time_To_Clean_Prediction.csv`

**Effort: S**

---

## Step 5 — Correlation & PCA (Exploratory, ทำคู่ขนานกับ Step 3/7 ได้)
**Objective:** หลักฐานสนับสนุน driver ของ fouling (ของเดิมดีอยู่แล้ว ไม่ต้องแก้ตรรกะ)

**สิ่งที่ต้องทำ:**
1. รวม `2_correlation.ipynb` + `2_pca.ipynb` เป็น `05_correlation_and_pca.ipynb`
2. อัปเดต input ให้ดึงจาก `Feature_Q.csv` (Step 2) และ `Fouling_Rate_Estimate.csv` (Step 3) แทน `Feature_calculated.csv` เดิม
3. คง PCA feature-reduction guidance เดิมไว้ (ตัด `Visc_50C`/`Visc_100C` และ `API`/`SG` คู่ collinear) ไปใช้ตอนเลือก feature ของ Step 7

**Effort: S**

---

## Step 7 — CIT Model Training (RF / XGBoost / LSTM)
**Objective:** โมเดลทำนาย CIT พร้อม train/validation/test แบบ chronological 3 ทาง

**สิ่งที่ต้องทำ:**
1. ใช้ feature matrix เดิม (`build_cit_feature_matrix`, 64 features, leak-free สำหรับ E113A) — ตัด collinear feature ตาม PCA guidance จาก Step 5
2. **เปลี่ยน split จาก 80/20 เป็น 3 ทาง** ตามหัวข้อ 4 ของแผนหลัก:
   - Train: 2024-01 → 2025-06
   - Validation: 2025-07 → 2025-12 (ใช้ tune hyperparameter + เลือกโมเดล)
   - Test: 2026-01 → ปัจจุบัน (แตะครั้งเดียวตอนจบ)
3. Time-series CV (walk-forward 5 folds) ภายใน Train+Validation สำหรับ hyperparameter search (ของเดิมมี TS-CV อยู่แล้วใน `6a` — ต่อยอด)
4. เทรน RF, XGBoost (primary), LSTM (benchmark เทียบเท่านั้น ไม่ใช้ production ตามที่สรุปในแผนหลัก เพราะแพ้ RF ขาดลอย)
5. รายงาน metric: **MAE, RMSE, %within±5°C, %within±10°C เป็นหลัก** — รายงาน R² พร้อม note เรื่อง variance ของช่วง test กำกับเสมอ (อย่ารายงาน R² เดี่ยวๆ โดยไม่มี context)
6. Save model artifacts (`joblib`/`keras`) — ใช้ต่อใน Step 8 และ Step 9 (what-if)

**Validation checklist:**
- [ ] ไม่มีการ tune hyperparameter หลังแตะ Test set แล้ว (lock ผลลัพธ์ทันทีที่ประเมิน Test ครั้งแรก)
- [ ] เทียบ metric ใหม่ (3-way split) กับของเดิม (80/20) — ควรใกล้เคียงกัน ถ้าต่างมากต้องอธิบายได้

**Effort: M**

---

## Step 8 — SHAP Importance & Cross-Validation
**Objective:** ยืนยันว่า HX ไหนมีน้ำหนักต่อ CIT มากที่สุด ด้วยวิธีที่ robust กว่า raw feature_importances_

**สิ่งที่ต้องทำ:**
1. ใช้โมเดล RF/XGBoost จาก Step 7 → `shap.TreeExplainer`
2. Aggregate |SHAP value| ต่อ HX (รวม 4 features ต่อ HX เป็นค่าเดียว)
3. Cross-check RF vs XGBoost SHAP ranking (Spearman correlation) — ของเดิมได้ 0.665 (ยอมรับได้ปานกลาง) ใช้เป็น confidence flag ถ้า rank ต่างกันมากในบาง HX ให้ธงไว้ว่า "ranking ไม่มั่นใจ" ในตาราง Step 6
4. Export `hx_cit_shap_importance.csv`

**Effort: S**

---

## Step 6 — Cleaning Priority Ranking (สูตรกลาง, รอ Step 3 + Step 8)
**Objective:** ranking เดียวไม่มีคำตอบคู่ขนานอีกต่อไป

**สิ่งที่ต้องทำ:**
1. ดึง `|fouling_rate|`, `confidence`, `rate_type` จาก Step 3
2. ดึง `cit_shap_importance` จาก Step 8 (แทน regression-slope เดี่ยวที่ใช้ใน `2c`/`2d` เดิม — ใช้ SHAP เป็นตัวหลัก, เก็บ regression-slope ไว้เป็น secondary/cross-check เท่านั้น)
3. คำนวณ `expected_CIT_gain` ต่อ HX (ยังคง caveat ของ CPHT-1 ไว้ตามหัวข้อ 3.4 ของแผนหลัก)
4. คำนวณ `coking_risk_score`, `residue_chain_risk` (คงสูตรเดิมจาก `2d`)
5. คำนวณ `effort_tier` (SWAP_CAPABLE / ONLINE_CLEAN_DEMONSTRATED / TAM_ONLY — คงเดิม)
6. รวมเป็น `engineering_priority` สูตรเดียวตามหัวข้อ 3.4
7. Export ตารางเดียว `Cleaning_Priority_Ranking.csv` — **นี่คือไฟล์ที่แทน `Engineering_Priority_Score.csv` และ `hx_Q_cleaning_priority_v2.csv` เดิมทั้งคู่**

**Decision point:** ยืนยันน้ำหนัก safety:energy (default 2:1) ตามที่ถามในแผนหลัก

**Effort: M**

---

## Step 9 — 12-Month Forecast, What-if CIT Target & Dashboard Export
**Objective:** ตอบคำถามสุดท้าย "clean ตัวไหนแล้ว CIT จะถึงเป้าไหม" + forecast ระยะยาวขึ้นจาก 6 เดือน → 12 เดือน

**สิ่งที่ต้องทำ:**
1. ขยาย linear/asymptotic extrapolation จาก Step 4 จาก 182 วัน → 365 วัน ต่อ HX
2. **What-if simulation ใหม่:**
   - รับ target CIT (°C) จากผู้ใช้ (decision point ในแผนหลัก หัวข้อ 7.4)
   - จำลอง: ถ้า clean HX ตัวที่ rank สูงสุดจาก Step 6 → ตั้งค่า Q_norm ของ HX นั้นกลับไปเป็น clean-state baseline (จาก Step 3) → feed ค่าใหม่เข้าโมเดล CIT (Step 7) → อ่าน ΔCIT ที่คาดว่าจะได้จริง
   - ทำซ้ำแบบ incremental (ลองเรียง clean HX ทีละตัวตาม rank) จนกว่า CIT ที่ predict ถึง target หรือ clean ครบทุกตัวที่เป็นไปได้ (ไม่เกิน effort/feasibility ที่มี)
   - Output: "ต้อง clean HX อะไรบ้างตามลำดับ ถึงจะถึง target CIT ที่ต้องการ"
3. Export dashboard JSON (`hx_ranking.json`, `forecast_12mo.json`, `model_metrics.json`, `cleaning_recommendations.json`, + ไฟล์ใหม่ `whatif_cit_target.json`)
4. อัปเดต dashboard (`dashboard/js/app.js`) ให้มี panel what-if ใหม่ (ต่อยอด ไม่ต้องรื้อ UI เดิม)

**Effort: M–L**

---

## สรุป Effort รวม (ลำดับทำจริง)

| ลำดับ | Step | Effort | เหตุผลที่ต้องทำก่อน/หลัง |
|---|---|---|---|
| 1 | 0/0b | S | ฐานของทุกอย่าง |
| 2 | 1 | S–M | ต้องมี case label ก่อนคำนวณ Q ที่ valid |
| 3 | 2 | S | ต้องมี Q function กลางก่อน Step 3/7 ใช้ต่อ |
| 4 | 3 | **L** | งานออกแบบใหม่หลัก — ควรเริ่มเร็วที่สุดเพราะใช้เวลานาน |
| 4 | 7 | M | ทำคู่ขนานกับ Step 3 ได้ (คนละ input) |
| 5 | 5 | S | คู่ขนานได้เช่นกัน (exploratory) |
| 6 | 4 | S | รอ Step 3 |
| 6 | 8 | S | รอ Step 7 |
| 7 | 6 | M | รอทั้ง Step 3 (rate) และ Step 8 (SHAP) |
| 8 | 9 | M–L | รอ Step 4 + 6 + 7 ทั้งหมด |

**จุดที่ควรเริ่มทำก่อนคือ Step 0/1/2 (เตรียมฐาน) แล้วเข้า Step 3 ทันที เพราะเป็นงานที่ใหญ่และเป็นต้นเหตุของความสับสนที่คุณรู้สึกมากที่สุด**

---
*รอ feedback ต่อจุด Decision point ที่ระบุไว้ในแต่ละ Step ก่อนเริ่มเขียนโค้ดจริง*
