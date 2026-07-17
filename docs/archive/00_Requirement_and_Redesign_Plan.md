# Requirement & Redesign Plan — CPHT Fouling / CIT Optimization
**เอกสารกำหนดความต้องการ (Requirement) และแผนปรับโครงสร้างการวิเคราะห์ทั้งระบบ**

Status: DRAFT v1 สำหรับให้ผู้ใช้ (วิศวกรเจ้าของโปรเจกต์) รีวิวก่อนเริ่มแก้ไข notebooks จริง
Prepared after full review of `notebooks/0_*` ถึง `6c_*`, `cpht_config.py`, `cpht_features.py`, `scratch_fouling/*`, และ dashboard exports ที่มีอยู่

---

## 1. ทำไมต้องรื้อแผนใหม่ (Problem Statement)

จากการสำรวจโค้ดทั้งหมด สิ่งที่ทำมาแล้ว**ไม่ได้ผิดหลักวิศวกรรม**และมีหลายส่วนที่ถูกต้องดี (เช่น การตรวจจับ operating state, สมการ Q แบบ cold-side) แต่ปัญหาหลักที่ทำให้ "ดูไม่ตรงกัน / ขัดกันเอง" คือ:

1. **มีคำนิยาม "fouling signal" อยู่ 4 ชุดที่ไม่ตรงกัน** กระจายอยู่คนละ notebook:
   - `2b_Q_duty_and_fouling`: slope เชิงเส้นของ `Q_norm` ต่อ campaign (%/30 วัน)
   - `3a/3b`: ML clean-state baseline แล้วดู deviation ของ `Q` (kW, ไม่ normalize)
   - `5_HX_fouling_CIT_ranking` / `6a-6c`: `Q_norm` แบบ campaign อีกชุดหนึ่ง (threshold/campaign detection คนละแบบกับ 2b) + โมเดล ML ทำนาย CIT
   - `scratch_fouling/test_fouling`: ใช้ **effectiveness (ε)** แทน Q ไปเลย
   
   ผลคือมี "อันดับความสำคัญของ HX ที่ต้อง clean" ออกมา 2 ชุดที่ไม่เท่ากัน (`2d`'s Engineering_Priority_Score vs `6c`'s SHAP-based priority_score) — นี่คือสิ่งที่ทำให้รู้สึกว่า "ขัดกัน"

2. **Case-Operate ของ HX ถูก encode ไว้ใน `2a` แล้วบางส่วน** (E101EF↔E101G, E113A↔E112C, E112AB bypass candidate) แต่ยังไม่ได้ทำเป็น "case label" ที่ตรงกับตรรกะ 3 กรณีที่ผู้ใช้ระบุมาโดยตรง (ดูหัวข้อ 3) — ต้องทำให้ตรงเป๊ะและมี output เดียวที่ใช้ต่อทุก notebook

3. **ไม่มีการแยก Initiation phase / After-initiation phase อย่างเป็นทางการ** — ปัจจุบันใช้ linear slope ตลอดทั้ง campaign ซึ่งใช้ได้กับ campaign สั้น (TAM-only) แต่ไม่เหมาะกับ HX ที่มี campaign เดียวยาวหลายปี (E101AB/CD/EF) ตามหลัก fouling curve ของ Kern-Seaton/Epstein

4. **ไม่มี Train/Validation/Test 3 ทางที่ชัดเจน** — ที่มีอยู่คือ chronological 80/20 (train/test) เท่านั้น ไม่มี validation set แยกสำหรับ tuning

**แนวทางแก้:** ยึด 1 คำนิยามเชิงวิศวกรรมต่อปริมาณ 1 ตัว, encode case-operate ให้ตรงกับของจริง 100%, แยกเฟส fouling ตามหลักวิชาการ, และจัด notebook เป็นไฟล์ Step เรียงลำดับเดียว ไม่มีของคู่ขนานที่ให้คำตอบต่างกัน

---

## 2. ขอบเขตระบบ (System Definition) — ยืนยันจากข้อมูลจริงในโค้ด

### CPHT-1 (ให้ความร้อนก่อน Desalter)
`E101AB, E101CD, E101EF, E101G, E102`
- E101AB / E101CD / E101EF คือ 3 branch คู่ขนานที่แบ่ง crude จาก `1TI102.pv`; แต่ละ tag เช่น "E101AB" ในข้อมูล **คือค่าที่วัดจากคู่ shell A+B ที่รันพร้อมกันอยู่แล้ว** (มี flow meter/thermocouple ของตัวเองเดี่ยว ไม่ต้องแยก A กับ B เพิ่ม) — ไม่ต้องแก้อะไรในส่วนนี้ เข้าใจตรงกันแล้ว
- **E101G เป็น spare ที่ไม่มี sensor เลย** ต้อง infer จาก mass balance: `Flow_G = total_charge − (FI007+FI008+FI009)` — เมื่อ E101EF หยุด (flow<10 m³/hr) และ inferred G flow>30 m³/hr → ถือว่า E101G กำลังทำงาน (offline, ไม่มีข้อมูลอุณหภูมิ) ตรงกับที่ผู้ใช้อธิบาย ("จะไม่มีข้อมูล แต่สาย feed ยังเข้าปกติ") — พบเหตุการณ์จริงยาว 136 วัน (18 ม.ค. 2026 เป็นต้นไป)

### CPHT-2 (ให้ความร้อนก่อนเข้าเตา F101)
`E106AB, E110ABC, E103AB, E107AB, E111, E104, E108AB, E112AB, E105AB, E112C, E109AB, E113A`

**Residue chain (ตัวที่ fouling เร็วสุด เพราะสัมผัส residue ร้อนจาก C101 bottoms):**
```
E113A(‖E112C) → E112AB → E108AB → E110ABC
```

**3 กรณี Case-Operate ที่ผู้ใช้ระบุ — เทียบกับโค้ดปัจจุบันใน `03_operating_state_classification.ipynb`:**

| กรณี | ผู้ใช้ระบุ | สถานะใน `2a` ปัจจุบัน | ต้องแก้/เสริม |
|---|---|---|---|
| **E113A cleaning** | E112C ทำหน้าที่แทน → รัน E112C, E112AB, E108AB | ตรวจจับได้จาก `1TI117.pv` (E113A) vs `1TI117B.pv` (E112C) เทียบ threshold 150°C — ได้ state `SUBSTITUTE_ACTIVE` ถูกแล้ว | เพิ่ม categorical label ชัดๆ ว่า `residue_chain_case = "E113A_CLEANING"` |
| **E112C cleaning** | E113A ทำงานตามปกติ → รัน E113A, E112AB, E108AB | ตรวจจับได้เช่นกัน (E112C idle <150°C) → state `NORMAL` (E113A) | เพิ่ม label `residue_chain_case = "E112C_CLEANING"` |
| **E112AB cleaning** | ใช้ E112C ทำหน้าที่แทน (bypass) → รัน E113A, E112C ทั้งคู่, E108AB | มี flag `E112AB_BYPASS_CANDIDATE` (threshold `1TI127.pv` dT<10°C) แต่ **ไม่พบเหตุการณ์จริงในข้อมูลปัจจุบันเลย (0 วัน)** | Logic เตรียมไว้แล้ว รอข้อมูลใหม่ที่มีเหตุการณ์นี้เกิดขึ้นจริงเพื่อยืนยัน threshold |

**สรุป:** ตรรกะ case-operate ที่ผู้ใช้อธิบายมา **ถูก encode ไว้แล้วเกือบสมบูรณ์** ใน `cpht_config.py` + `2a` เพียงแต่ยังไม่ได้ทำเป็น output column เดียวที่อ่านง่าย และยังไม่เคย validate กรณีที่ 3 กับข้อมูลจริง → นี่คือหนึ่งใน Step ที่ต้องทำใหม่ให้สมบูรณ์ (ดู Step 1 ในหัวข้อ 6)

### E101EF ↔ E101G
ตรงกับที่ผู้ใช้อธิบาย 100%: หยุด E101EF → ใช้ E101G ทดแทนแบบ offline/ไม่มี sensor → data จะไม่ปกติ (ไม่มีข้อมูลอุณหภูมิ E101G) แต่ total crude feed ที่เข้าระบบยังเข้าปกติ (วัดที่ `1fi005.pv`) — โค้ดปัจจุบันจัดการถูกแล้วด้วย mass-balance inference

---

## 3. หลักวิศวกรรมที่จะใช้เป็นมาตรฐานเดียว (Canonical Engineering Method)

### 3.1 Heat Duty (Q) — cold-side only (คงไว้ตามเดิม ถูกต้องแล้ว)
เหตุผล: hot-side sensor (residue/gas oil/kerosene side) มีปัญหาคุณภาพข้อมูลมาก และมีการสลับ shell ทำให้ signal ปนกัน — cold-side (crude) วัดได้ต่อเนื่องเสมอไม่ว่า HX ไหนทำงานอยู่

```
T_avg = (T_in + T_out) / 2
Cp    = (1.685 + 0.00339·T_avg) / sqrt(SG)        [Watson–Nelson, kJ/kg·K]
ρ(T)  = ρ15.6 · exp[−α(T_avg−15.6)(1+0.8α(T_avg−15.6))]   [ASTM D1250/Rackett]
mdot  = Flow[m³/h] · ρ(T) / 3600                   [kg/s]
Q     = mdot · Cp · (T_out − T_in)                 [kW]
Q_norm = Q / total_charge                          [ใช้ตัด effect ของ throughput ออก]
```
ยืนยัน: สมการนี้เหมือนกันทั้ง `2b` และ `5` — **เป็นจุดร่วมที่ถูกต้องอยู่แล้ว ไม่ต้องแก้**

### 3.2 ทำไมไม่ใช้ Rf (fouling resistance, m²·K/W) เป็นตัวหลัก
หลักวิศวกรรมเคมีที่ถูกต้องคือ Rf = 1/U − 1/U_clean ซึ่งต้องรู้ U จริง (ต้องมี hot-side ΔT/flow ที่เชื่อถือได้) — **ข้อมูล hot-side ของโรงงานนี้ไม่น่าเชื่อถือพอ** (ตามที่ทั้งผู้ใช้และ `0_profiling_process_control` ระบุตรงกัน) ดังนั้น:

- **ใช้ `Q_relative` deviation จาก clean-state baseline model เป็น proxy หลักของ fouling severity** (ตามแนวทางที่ `3a` เคย reference ไว้แล้ว: Ujevic Andrijic & Rimac, Sensors 2025 — เรียนรู้ Q ที่ "ควรจะเป็น" ภายใต้ flow/T ปัจจุบันจากช่วง clean-state แล้ววัด deviation)
- เมื่อมีข้อมูล hot-side ที่เชื่อถือได้ (เช่น ช่วงที่ shell คู่ทำงานปกติทั้งคู่พร้อมกัน) ให้คำนวณ Rf จริงเป็น **cross-check เท่านั้น** ไม่ใช่ตัวเลขหลักที่ใช้ตัดสินใจ
- เปลี่ยนคำเรียกจาก "Rf" เป็น **"Fouling Severity Index (FSI)"** ในรายงาน เพื่อไม่ให้สื่อว่าเป็นค่า Rf ทางฟิสิกส์ที่แม่นยำ

### 3.3 Initiation phase / After-initiation phase / Fouling Rate Estimation
ตามหลัก fouling curve แบบ Kern-Seaton (asymptotic) และ Epstein:

- **Initiation phase**: ช่วง ~14–30 วันแรกหลัง cleaning event ที่ deposit ยังเกาะไม่มาก, Q ยังใกล้ baseline สูงสุด — ใช้สร้าง **clean-state baseline model** (ตาม 3.2) จากช่วงนี้เท่านั้น ไม่เอาไปรวมกับช่วง fouling หลัก
- **After-initiation (fouling) phase**: หลังจากนั้น fit ด้วย 2 โมเดลแล้วเลือกด้วย AIC/R² per campaign:
  1. **Linear (falling-rate) model**: `Q_norm(t) = a + b·t` — ใช้ได้ดีกับ campaign สั้น (TAM-only HX เช่น E101AB, E105AB, E111, E110ABC ที่มี 0–1 online clean)
  2. **Kern-Seaton asymptotic model**: `deviation(t) = D∞·(1 − exp(−t/τ))` — เหมาะกับ HX ที่มี campaign ยาวต่อเนื่องหลายปี (E101AB/CD/EF ปัจจุบันมี 1 campaign ยาวมาก slope เกือบแบน 1%) เพราะ fouling จริงมักจะ "อิ่มตัว" ไม่ลดต่อเนื่องเป็นเส้นตรงตลอดไป
- **Fouling Rate Estimation ที่ export ออกมาต่อ HX ต่อ campaign**: `rate_type` (linear/asymptotic), `rate_value`, `R²`, `n_points`, `confidence` (จำนวน cleaning event ในอดีตที่มี)

### 3.4 Cleaning Priority Ranking — รวมเป็น 1 สูตรเดียว
ยึดโครงสร้างจาก `2d` (ครบมิติที่สุด: energy value + safety + feasibility) เป็นสูตรกลาง แต่แทนที่ CIT-sensitivity ที่ประมาณจาก regression เดี่ยว ด้วย **SHAP importance จากโมเดล CIT ML** (จาก `6b`) เป็น cross-check/น้ำหนักเสริม:

```
probability_score  = |fouling_rate| × confidence_weight × trajectory_multiplier
consequence_score  = w1·normalize(expected_CIT_gain) + w2·safety/coking_flag
                      (ปรับ w1,w2 ตามนโยบายที่ผู้ใช้ยืนยัน — ปัจจุบัน default w2=2×w1)
engineering_priority = (probability_score × consequence_score) / effort_penalty
```
โดย `expected_CIT_gain` ยังต้องคง caveat ของ CPHT-1 (E101AB/CD, E102) ว่าความเชื่อมั่นต่ำ เพราะไม่มี desalter-outlet temperature วัดตรง (ผลกระทบต่อ CIT เป็นทางอ้อมผ่าน desalter)

**ผลลัพธ์:** เหลือ ranking ตารางเดียว ไม่มี "2 คำตอบที่ต่างกัน" อีกต่อไป

---

## 4. Data Split Strategy (Train / Validation / Test)

แบบ **chronological 3-way split** (ห้าม random shuffle เพราะเป็น time series ที่มี autocorrelation และ crude batch เปลี่ยนเป็นช่วงๆ):

| Set | ช่วงเวลา (ตัวอย่างจากข้อมูลปัจจุบัน 2024-01→2026-06) | ใช้ทำอะไร |
|---|---|---|
| **Train** | 2024-01-01 → 2025-06-30 (~18 เดือน) | fit โมเดล (RF/XGB/LSTM) |
| **Validation** | 2025-07-01 → 2025-12-31 (~6 เดือน) | tune hyperparameter, เลือกโมเดล/feature set, เลือก linear vs Kern-Seaton ต่อ HX |
| **Test** | 2026-01-01 → ปัจจุบัน (~6 เดือน) | ประเมินครั้งสุดท้ายเท่านั้น ห้ามย้อนไป tune ซ้ำ |

เสริมด้วย **time-series cross-validation (walk-forward, 5 folds)** ภายใน Train+Validation เพื่อความมั่นใจของ hyperparameter ก่อนแตะ Test — ต่อยอดจากที่ `6a` มี TS-CV อยู่แล้ว

**เรื่อง metric ที่ต้องระวัง (พบใน `5`/`6a`):** R² ติดลบในช่วง Test เพราะช่วงนั้น CIT มี variance ต่ำ (σ≈2.6°C) เทียบกับ Train (σ≈7.6°C) — ไม่ได้แปลว่าโมเดลแย่ ให้ใช้ **MAE, RMSE, และ %within±5°C/±10°C** เป็น metric หลักในรายงาน (ตาม spec เดิมที่มี) และรายงาน R² แบบมี context เตือนเรื่อง variance กำกับไว้เสมอ

---

## 5. Model Plan (LSTM / RF / XGBoost)

จากผลที่มีอยู่ (`6a`, `6b`): **RandomForest ชนะ LSTM ขาด** (within±10°C: RF 95.8% vs LSTM 50.9%) เพราะ fouling signal เปลี่ยนช้าเป็นวันๆ ไม่มี sequence pattern ที่ LSTM จะได้เปรียบ — คงทิศทางนี้ไว้:

- **Primary models**: RandomForest, XGBoost (tree-based, ตีความง่าย, SHAP ได้ตรง)
- **LSTM**: เก็บไว้เป็น benchmark เปรียบเทียบเท่านั้น ไม่ใช้เป็นโมเดล production เพราะ error สูงกว่า RF ~60% และ permutation importance ไม่ให้ signal ที่มีประโยชน์
- **Feature set**: ใช้ 64-feature leak-free matrix ที่มีอยู่ (`cpht_features.build_cit_feature_matrix`) เป็นฐาน — ตัด collinear pair ที่พบจาก PCA (`Visc_50C` vs `Visc_100C` r=0.97, `API` vs `SG` r=-0.98 → เก็บตัวเดียวต่อคู่)
- **SHAP**: ใช้ยืนยัน HX ไหนมีน้ำหนักต่อ CIT มากที่สุด (ปัจจุบัน: E101AB, E101EF, E103AB, E105AB สูงสุด) แล้วป้อนกลับเข้า Cleaning Priority Ranking (หัวข้อ 3.4) เป็น cross-check
- **สิ่งที่ต้องตอบให้ได้ตามที่ผู้ใช้ระบุ**: "การ Cleaning ตัวไหนจะทำให้ CIT ถึงค่าที่ต้องการได้ไหม" → หลังมีโมเดล CIT + fouling-rate forecast แล้ว ทำ **what-if simulation**: จำลอง Q_norm ของ HX ที่จะ clean กลับไปเป็นค่า baseline (clean-state) แล้ว feed เข้าโมเดล CIT เพื่อดู ΔCIT ที่คาดว่าจะได้จริง เทียบกับ target CIT ที่ต้องการ

---

## 6. โครงสร้าง Notebook ใหม่ (Step files) — เสนอลำดับเดียว ไม่มีของคู่ขนาน

| Step | ชื่อไฟล์ใหม่ | มาจาก (เก็บ/รวม) | สถานะ |
|---|---|---|---|
| **Step 0** | `00_data_ingestion_and_cleaning.ipynb` | รวม `0_profilling_Crude` + `1_cleaning_data_process` | เก็บของเดิม ปรับแค่ merge ให้เป็นไฟล์เดียว logic ถูกต้องอยู่แล้ว |
| **Step 0b** | `00b_process_profiling.ipynb` | `0_profiling_process_control` (EDA อย่างเดียว ไม่ export อะไรที่ downstream ใช้) | เก็บไว้เป็น EDA reference |
| **Step 1** | `01_case_operate_state.ipynb` | `2a_operating_state_classification` + เพิ่ม categorical `residue_chain_case` label ตามหัวข้อ 2 | ปรับเสริม ไม่ต้องเขียนใหม่ทั้งหมด |
| **Step 2** | `02_engineering_features_Q.ipynb` | `2_Feature_calculation` + สมการ Q จาก `2b`/`5` (ให้เหมือนกันแหล่งเดียว) | รวมให้เหลือจุดคำนวณ Q จุดเดียว |
| **Step 3** | `03_fouling_phase_and_rate.ipynb` | แทนที่ `2b` (campaign-linear) + `3a` (ML baseline) ด้วยกรอบเดียว: Initiation-phase baseline (ML, จาก 3a) + After-initiation rate fit เลือก linear/Kern-Seaton (หัวข้อ 3.3) | **เขียนใหม่บางส่วน** — รวม 2 แนวทางเดิมให้เป็นกรอบเดียวตามหลักวิชาการ |
| **Step 4** | `04_time_to_clean_forecast.ipynb` | `3b_time_to_clean_prediction`, ใช้ output จาก Step 3 | ปรับ input source เท่านั้น logic เดิมใช้ได้ |
| **Step 5** | `05_correlation_and_pca.ipynb` | `2_correlation` + `2_pca` | เก็บของเดิม เป็น exploratory/supporting evidence |
| **Step 6** | `08_cleaning_priority_ranking.ipynb` | รวม `2c` + `2d`, ตัดส่วนซ้ำกับ `5` | ใช้สูตรกลางตามหัวข้อ 3.4 |
| **Step 7** | `07_cit_model_training.ipynb` | รวม `5` (ML ส่วน CIT) + `6a` | ใช้ Train/Val/Test 3 ทาง (หัวข้อ 4) แทน 80/20 |
| **Step 8** | `08_shap_and_validation.ipynb` | `6b_shap_importance_ranking` | เก็บของเดิม เชื่อมกลับเข้า Step 6 |
| **Step 9** | `09_forecast_and_dashboard_export.ipynb` | `6c_six_month_forecast_and_dashboard_export`, ขยายเป็น 12 เดือน + what-if CIT-target simulation (หัวข้อ 5) | ต่อยอดของเดิม เขียนเพิ่มเฉพาะ what-if section |
| — | `scratch_fouling/*` | เก็บเป็น archive/validation เท่านั้น (ผลตรงกับ Step 7 อยู่แล้ว ไม่ใช้เป็น production) | ไม่ต้องแก้ ย้ายไป `notebooks/archive/` |

**สิ่งที่ต้อง "เขียนใหม่จริงๆ" มีแค่ Step 1 (เสริม), Step 3 (รวมกรอบ), Step 6 (รวมสูตร), Step 9 (เพิ่ม what-if)** — ที่เหลือคือย้าย/รวมไฟล์และเปลี่ยน input path เท่านั้น ไม่ต้องเขียนโค้ดคำนวณใหม่จากศูนย์ เพราะของเดิมถูกต้องเชิงวิศวกรรมอยู่แล้วในหลายจุด

---

## 7. สิ่งที่ต้องขอข้อมูล/คำยืนยันจากผู้ใช้ก่อนเริ่ม implement

1. **น้ำหนัก safety vs energy ใน priority score** (ปัจจุบัน default safety = 2× energy) — ยืนยันหรือปรับ
2. **NEXT_TAM_DATE** ปัจจุบันเป็น placeholder `2028-06-01` ใน `3b` — วันที่จริงคือเมื่อไหร่
3. **Desalter outlet temperature tag** (ถ้ามี) เพื่อลด uncertainty ของ CPHT-1 (E101AB/CD, E102) CIT-gain estimate
4. **CIT target ที่ต้องการ** (ตัวเลข °C) สำหรับทำ what-if simulation ใน Step 9
5. **Cleaning log ย้อนหลัง** (ก่อน 2024 ถ้ามี) เพื่อเพิ่มจำนวน campaign ให้ HX ที่มี event น้อย (เช่น TAM-only บางตัวมี 0-1 event ทำให้ threshold ไม่แม่น)

---

## 8. ลำดับการทำงานที่แนะนำ (ถ้าอนุมัติแผนนี้)

1. Step 1 (case-operate label) → ใช้เวลาน้อย ผลกระทบสูง เป็นฐานของทุก step ถัดไป
2. Step 3 (fouling phase framework ใหม่) → เป็นจุดที่ user รู้สึกว่า "ไม่ตรง" มากที่สุด แก้ก่อนจะเคลียร์ความสับสนได้เร็วที่สุด
3. Step 6 (รวม ranking เป็นสูตรเดียว)
4. Step 7 (ปรับ train/val/test)
5. Step 9 (what-if + 12-month forecast)
6. Step 0/2/4/5/8 (ย้ายไฟล์/รวมไฟล์ ทำหลังสุดเพราะเป็นงาน house-keeping ไม่กระทบผลลัพธ์)

---
*เอกสารนี้เป็น requirement/design เท่านั้น ยังไม่มีการแก้ notebook จริง — รอ feedback ก่อนเริ่ม Step ใดๆ*
