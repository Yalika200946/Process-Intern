# Requirement v2 — Single Source of Truth (SSOT)
## CPHT Fouling → CIT Optimization · Plant 3 TPU · Bangchak

สถานะ: **DRAFT v2 — รออนุมัติก่อนแก้ notebook จริง**
เอกสารนี้ **รวมและแทนที่** `00_Requirement_and_Redesign_Plan.md` + `01_Stepwise_Execution_Plan.md`
โดยเพิ่ม/ล็อก "ตรรกะ case-operate" ตามที่วิศวกรเจ้าของโปรเจกต์ยืนยันล่าสุด และแก้จุดที่เคยไม่ตรงกัน
จัดทำหลังสำรวจ `notebooks/0_*→6c_*`, `cpht_config.py`, `cpht_features.py`, `docs/00,01`, `Data/*`, dashboard/figures ทั้งหมด

---

## 1. สรุปการสำรวจ (ของเดิมมีอะไร และถูกต้องแค่ไหน)

| ส่วน | สถานะ | ใช้ต่อได้ไหม |
|---|---|---|
| `cpht_config.py` (HX layout, E113A∥E112C, E101G no-sensor, chain predecessor) | ถูกต้อง | ✅ เป็นฐาน SSOT ของ config |
| `cpht_features.py` (`compute_q_features`, `build_cit_feature_matrix` 64 feat leak-free) | ถูกต้อง | ✅ ใช้ต่อ |
| Q แบบ cold-side (Watson–Nelson Cp, Rackett ρ, Q_norm) | ถูกต้อง เหมือนกันทั้ง 2b/5 | ✅ ย้ายเป็นฟังก์ชันเดียว |
| operating-state (2a): E101EF↔E101G mass-balance, E113A↔E112C 150 °C | ถูกต้อง | ✅ ต่อยอดเพิ่ม label |
| ข้อมูล `Data/` (process+crude, Operating_State, Feature_Q, assay 2017–21) | มีครบ | ✅ |
| **ปัญหา:** fouling signal 4 นิยาม / ranking 2 ชุด / ไม่มี Initiation-phase ทางการ / split 80–20 | ต้องแก้ | ⚠️ = เหตุที่ "รู้สึกขัดกัน" |

**หลักการแก้:** 1 ปริมาณ = 1 นิยามเชิงวิศวกรรม, case-operate = output เดียว, แยกเฟส fouling ตามหลักวิชาการ, split เป็น train/val/test, และ notebook เรียงเป็น Step เดียวไม่มีของคู่ขนานที่ให้คำตอบต่างกัน

---

## 2. นิยามระบบ & การจัดวาง HX (LOCKED)

**สัญลักษณ์:** ชื่อ HX ที่ลงท้ายหลายตัวอักษร = shell ที่รัน **ขนานกันเป็นชุดเดียว** และมีมิเตอร์/เทอร์โมคัปเปิลของชุดนั้นอยู่แล้ว —
`E101AB = E101A + E101B`, `E110ABC = E110A + E110B + E110C` ฯลฯ → ในข้อมูลถือเป็น 1 หน่วย ไม่ต้องแยก A/B

### CPHT-1 (ให้ความร้อน crude ก่อนเข้า Desalter)
`E101AB · E101CD · E101EF · E101G · E102`
- E101AB/CD/EF = 3 branch ขนานแบ่ง crude จาก `1TI102`
- **E101G = spare แบบ offline ไม่มี sensor เลย** → เมื่อ E101EF หยุด จะใช้ E101G แทน; ข้อมูลอุณหภูมิ/flow ของ G จะหาย แต่ Total Crude (`1fi005`) ยังเข้าปกติ → ต้อง infer ด้วย mass balance: `Flow_G ≈ total − (FI007+FI008+FI009)`

### CPHT-2 (เพิ่ม CIT ก่อนเข้าเตา F101 — มีผลต่อพลังงาน + อายุเตา)
`E106AB · E110ABC · E103AB · E107AB · E111 · E104 · E108AB · E112AB · E105AB · E112C · E109AB · E113A`

### สาย Residue (fouling เร็วสุด — สัมผัส residue ร้อนจาก C101 bottoms, cleaning บ่อย)
ลำดับ **series** ที่ถูกต้อง (E112C เป็น "ตำแหน่งเดียวกับ" E113A แบบขนาน ไม่ใช่อนุกรมถัดจากกัน):

```
( E113A  ∥  E112C )  →  E112AB  →  E108AB
       ตำแหน่งเดียวกัน       ถัดไป      ถัดไป
   cold_in 1TI115 → cold_out 1TI116 (=CIT)
```
> หมายเหตุแก้จาก doc 00: เขียนให้ชัดว่า E113A กับ E112C = ตำแหน่งเดียวกัน (parallel alternates, `cold_in=1TI115`, `cold_out=1TI116`) แล้วจึงไป E112AB → E108AB

---

## 3. ตรรกะ Case-Operate (LOCKED — ตามที่วิศวกรยืนยัน)

ทุก notebook ต้องอ่าน case จาก **คอลัมน์เดียว** `residue_chain_case` ใน `Operating_State.csv` (Step 1 เป็นผู้สร้าง)

| Case | เงื่อนไข (จากข้อมูล) | HX ที่ทำงาน | สถานะข้อมูล |
|---|---|---|---|
| **NORMAL** | E113A active, E112C idle (`1TI117B`<150 °C) | E113A → E112AB → E108AB | ปกติ |
| **E113A_CLEANING** | E113A idle, E112C active (`1TI117B`≥150 °C แทน `1TI117`) | **E112C** → E112AB → E108AB | E112C ทำแทน (ข้อมูล cold ต่อเนื่องที่ 1TI116) |
| **E112C_CLEANING** | E112C idle, E113A active | E113A → E112AB → E108AB | แยกจาก NORMAL ได้ต่อเมื่อมี **cleaning log** เท่านั้น |
| **E112AB_CLEANING (bypass)** | E112AB dT เล็ก (`1TI127` dT<10 °C) | **E113A + E112C ทั้งคู่** → (bypass E112AB) → E108AB | ยังไม่พบเหตุการณ์จริงในข้อมูล (0 วัน) — เตรียม logic รอ |
| **E101EF→E101G** | E101EF flow<10 & inferred G flow>30 | E101G (offline, ไม่มีอุณหภูมิ) | ข้อมูลผิดปกติ 136 วัน (พบจริง) — mask ออกจากการ fit |

**กติกา QA:** ห้ามมีวันที่ E113A และ E112C off พร้อมกัน (สาย residue จะไม่มีอะไรวิ่ง = error)

---

## 4. วิธีเชิงวิศวกรรมมาตรฐานเดียว (Canonical Method)

1. **Heat duty (Q) — cold-side only** (เพราะ hot-side ไม่สมบูรณ์/abnormal เยอะ): `T_avg→Cp(Watson–Nelson)→ρ(Rackett)→ṁ→Q=ṁ·Cp·ΔT`, แล้ว `Q_norm=Q/total_charge` (ตัด throughput). ทำเป็น **ฟังก์ชันเดียว** ใน `cpht_features.py`
2. **Fouling severity = Q deviation จาก clean-state baseline** (ไม่ใช้ Rf เป็นตัวหลักเพราะต้องพึ่ง hot-side ที่ไม่น่าเชื่อถือ) เรียก **FSI (Fouling Severity Index)**; คำนวณ Rf จริงเป็น cross-check เฉพาะช่วงที่ hot-side ครบ
3. **เฟส fouling:** *Initiation phase* (~0–21 วันหลัง clean → ใช้สร้าง baseline ML เท่านั้น) และ *After-initiation phase* (fit อัตราด้วย **Linear** หรือ **Kern–Seaton** `D∞(1−e^(−t/τ))` เลือกด้วย AIC) → export `rate_type, rate_value, R², confidence`
4. **Q ↔ CIT:** ใช้พิจารณาว่า HX ตัวไหน "ขยับ CIT" จริง → ป้อนเข้า ranking
5. **Data split (chronological, ห้าม shuffle):** Train 2024-01→2025-06 · Validation 2025-07→2025-12 · Test 2026-01→ปัจจุบัน + walk-forward CV ใน Train+Val. metric หลัก = **MAE, RMSE, %within±5/±10 °C** (R² รายงานพร้อม context variance)
6. **Models:** RF + XGBoost (primary, ตีความด้วย SHAP), LSTM (benchmark เท่านั้น — แพ้ RF: within±10 °C 95.8% vs 50.9%)
7. **Cleaning Priority (สูตรเดียว):** `priority = probability(|rate|×confidence×trajectory) × consequence(w1·CIT_gain + w2·safety/coking) / effort` — ใช้ SHAP เป็นน้ำหนัก CIT-gain หลัก
8. **What-if (คำถามปลายทาง):** จำลอง clean HX (ตั้ง Q_norm กลับเป็น baseline) → feed โมเดล CIT → อ่าน ΔCIT → บอกว่าต้อง clean ตัวไหนบ้างตามลำดับถึงจะได้ CIT ถึงเป้า

---

## 5. โครงสร้าง Notebook แบบแยก Step (เป้าหมาย — ปรับจากของเดิม ไม่เขียนใหม่หมด)

| Step | ไฟล์ใหม่ | มาจาก | งาน |
|---|---|---|---|
| 0 | `00_data_ingestion_and_cleaning.ipynb` | `0_profilling_Crude` + `1_cleaning_data_process` | รวมไฟล์ (logic เดิม) |
| 0b | `00b_process_profiling.ipynb` | `0_profiling_process_control` | EDA reference |
| 1 | `01_case_operate_state.ipynb` | `2a` + เพิ่ม `residue_chain_case` (หัวข้อ 3) | ต่อยอด |
| 2 | `02_engineering_features_Q.ipynb` | `2_Feature_calculation` + Q เดียวจาก `cpht_features` | refactor |
| 3 | `03_fouling_phase_and_rate.ipynb` | แทน `2b`+`3a` ด้วยกรอบ Initiation/After-initiation | **เขียนใหม่หลัก (L)** |
| 4 | `04_time_to_clean_forecast.ipynb` | `3b` | เปลี่ยน input |
| 5 | `05_correlation_and_pca.ipynb` | `2_correlation` + `2_pca` | รวม (exploratory) |
| 6 | `08_cleaning_priority_ranking.ipynb` | `2c` + `2d` (สูตรเดียว + SHAP) | รวม |
| 7 | `07_cit_model_training.ipynb` | `5` + `6a` (train/val/test) | ปรับ split |
| 8 | `08_shap_and_validation.ipynb` | `6b` | ต่อ |
| 9 | `09_forecast_whatif_dashboard.ipynb` | `6c` + what-if + 12-month | ต่อยอด |

**ลำดับลงมือ (ตาม dependency):** `0/0b → 1 → 2 → {3, 7} → {4, 8} → 6 → 9`
**เขียนใหม่จริงเฉพาะ:** Step 1 (เสริม label), Step 3 (กรอบเฟส), Step 6 (รวมสูตร), Step 9 (what-if) — ที่เหลือคือย้าย/รวม/เปลี่ยน path

---

## 6. Decision points ที่ต้องยืนยันก่อนเริ่มเขียนโค้ด

1. **Cleaning / maintenance log ย้อนหลัง** (วันที่ clean จริงต่อ HX) — จำเป็นมาก: ใช้แยก `E112C_CLEANING` จาก `NORMAL`, ยืนยัน campaign boundary (Step 3), และ validate FSI reset
2. **น้ำหนัก safety : energy** ใน priority (default 2:1) — ยืนยัน/ปรับ
3. **NEXT_TAM_DATE** จริง (ปัจจุบัน placeholder 2028-06-01)
4. **Target CIT (°C)** ที่ต้องการ สำหรับ what-if (Step 9)
5. **Desalter-outlet temp tag** (ถ้ามี) — ลด uncertainty ของ CIT-gain ฝั่ง CPHT-1

---

## 7. Next action ที่แนะนำ
เริ่มที่ **Step 0 → 1 → 2** (เตรียมฐาน + ล็อก case label + Q ฟังก์ชันเดียว) แล้วเข้า **Step 3** ทันที (เป็นงานใหญ่และเป็นต้นเหตุความสับสนที่สุด) โดยทำเป็นไฟล์ Step แยกชัดเจน ปรับจากของเดิมทีละขั้น พร้อม validation checklist ต่อ Step

*เอกสาร requirement/design เท่านั้น — ยังไม่มีการแก้ notebook จริง รอ feedback ต่อ Decision points ข้อ 1–5*
