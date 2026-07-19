# CPHT Fouling & Cleaning — Analysis Methodology & Honest Findings

ระเบียบวิธีของ notebook 0–6 (อ่านคู่กับแต่ละ notebook) — เขียนให้ตรงแบบที่ data/process engineer
วิเคราะห์อย่างเป็นระบบ พร้อม **ยอมรับข้อจำกัดตรง ๆ**

## 1. Pipeline (ลำดับ dependency)
```
0 profiling ─┐
1 cleaning ──► 2 features ─► 2a state ─► 2b Q/fouling ─► 2c Q-CIT ─┐
                                                                   ├─► 2d cleaning rank ─┐
              3a forecast(deviation) ─► 3b time-to-clean ──────────┘                     │
              5 CIT rank · 6a model-benchmark · 6b SHAP · 6d clean-ΔCIT ─────────────────┤
                                                                                          ▼
                                                        6c export ─► dashboard/data/*.json
                                                        + post: gen_honest_metrics, add_forecast_intervals,
                                                                build_dashboard_topology, phm_analysis
```
รันทั้งหมด: `python pipeline/run_all.py` (UTF-8 mode, backup อัตโนมัติ, post-process ให้ผลตรง)

## 2. เครื่องมือมาตรฐาน (`nb_audit.py`) — reuse ทุก notebook
- `data_quality_report` — missing %, range, duplicates, time-gaps (gate ก่อน model)
- `leave_run_out_cv` / `naive_rate_baseline_cv` — validation ที่ซื่อสัตย์ (hold out ทั้ง run/HX + เทียบ baseline)
- `plausibility_checks` — invariant ทางฟิสิกส์ (ΔT>0, Q>0, cold_out>cold_in)
- `quality_gate_runs` — ธง/คัดรอบ fouling-rate ที่ R²/N ต่ำ

## 3. ข้อค้นพบสำคัญ (รายงานตรง ๆ — นี่คือหัวใจของความเป็นระบบ)

**(A) โมเดล CIT ไม่ชนะ persistence** — walk-forward CV (6a): persistence (CIT วันนี้=เมื่อวาน)
CV R²≈**+0.80**, XGBoost CV R²≈**−2.8** (แพ้ทุก fold, skill −308%). single-split R²=0.82 เป็น artifact.
→ tree ใช้ **SHAP attribution เท่านั้น** (associative) ไม่ใช่ตัวพยากรณ์. (dashboard model card + 5 §9 + 6b มี caveat)
**Ablation ที่ทดสอบแล้ว (6a §6b):** ลอง**ตัด `CIT_lag1`/`CIT_roll7` ออก** (ใช้ HX/crude feature ล้วน) →
CV R² **แย่ลงอีก (−4.63 vs −2.79 ตอนมี lag)** — ไม่ใช่จุดบั๊กที่ต้องแก้ `CIT_lag1` คือเหตุผลเดียวที่โมเดลยังใกล้เคียงระดับ CIT
เพราะ HX/crude feature ล้วน ๆ อธิบาย**ระดับ CIT** ไม่ได้เลย (คนละคำถามกับ "อะไรมีผลต่อ CIT" ที่ SHAP ตอบ). แสดงใน
dashboard model card (role=`ablation`) ด้วย

**(B) การพยากรณ์ fouling ข้าม HX ไม่ generalize** — 3a leave-HX-out CV R²≈**+0.10** (Q scale ต่างกันมากต่อ HX).
สัญญาณที่ deploy ยังใช้ได้เพราะ refit บน pool รวม baseline ของ HX นั้นเอง — **ไม่ใช่ zero-shot**. (3a §7 + honest-read cell)

**(C) ข้อมูลเล็ก** — 96 run (2–6/HX, ชุดข้อมูล 2021-2026). quality gate ติดธง **32/96 run** ที่ R²<0.3. per-HX Weibull ที่ n<4 ใช้ pooled shape.
driver analysis n=45 → **CV R²≈−5.7 (<0) = associative ไม่ใช่ causation**. (phm_analysis + dashboard caveat · ตัวเลข live ดูแท็บ "หลักฐาน & ความเชื่อมั่น" / `evidence.json`)

**(D) Cleaning logic (2d) — redesign** — consequence เดิมพึ่ง CIT model ที่ไม่แม่น + min-max ทำให้ HX เดียวครอบงำ.
แก้เป็น: consequence = **Q-duty shortfall ที่วัดได้** (หลัก) + safety, CIT-gain เหลือ weight 0.25;
normalize แบบ **rank-percentile** → คะแนนกระจายอ่านได้ (E113A=1.00, #2=0.93 แทน 0.15).

## 4. สมมติฐานหลัก + ข้อจำกัด (ทั้งโปรเจกต์)
- Q = ṁ·Cp·ΔT ด้วย **Cp=2.2, ρ=850 คงที่** (ไม่ขึ้นกับ T/crude) — ใช้เชิงเปรียบเทียบ (U_relative/Q_drop) จึงยอมรับได้
- **hot-side เป็น confound ที่ละไว้** — ไม่มี per-HX hot flow (residue path ใช้ร่วม/สลับ)
- ไม่มี **ground-truth Rf** — validate ด้วย reset-หลังล้าง (3a §5) เท่านั้น
- crude-batch effect n=2–6 (p>0.15) → inconclusive, ใช้ structural chain-position แทน
- NEXT_TAM + LHV/efficiency เป็น input ปรับได้ (dashboard), ยังไม่ยืนยันค่าจริง

## 5. ทำไมเชื่อผลได้แม้ข้อจำกัดเยอะ
จัดลำดับล้างอิง **สัญญาณกายภาพที่วัดได้** (Q-duty drop, fouling rate, ตำแหน่งในเทรน, safety) เป็นหลัก —
ไม่พึ่งโมเดลที่ยัง validate ไม่ผ่าน. ทุกโมเดลที่แสดงมี **baseline เทียบ + CV ที่ hold out จริง + ธงความเชื่อมั่น**
ตามหลัก "อย่า overclaim" อย่างสม่ำเสมอ

## 6. Dashboard v2 — End-of-Run, Simulation, Advisory, Economics (เพิ่ม 2026-07)

หน้าเว็บ (`dashboard/index.html`, เสิร์ฟที่ :8811) เพิ่มความสามารถต่อไปนี้ พร้อม "Basis" (ⓘ ที่มาการคำนวณ) กำกับใต้ทุกกราฟ:

### 6.1 End-of-Run duty forecast (แท็บ HX รายตัว)
สลับดูได้ 2 มุมมอง (toggle) จาก `pipeline/export_end_of_run.py` → `end_of_run.json`:
- **Fouling view (ตัวตัดสิน trigger):** U_relative = U/U_clean (1.0 = สะอาด, ไม่ขึ้นกับ throughput).
  เกณฑ์ล้าง = `1 − TRIGGER_DROP_FRAC` (0.125 → **0.875**) ตาม notebook 5.
- **Duty view (ผลกระทบ):** Q duty จริง [kW] เทียบ Q สภาพสะอาด; เกณฑ์ = `clean_Q − threshold_shortfall` (จาก 3b).
- เวลาเหลือ = extrapolate เชิงเส้นของรอบเดินเครื่องปัจจุบัน (วิธีเดียวกับ `Time_To_Clean_Prediction.csv`).
- **การป้องกัน rate ค้าง (rate_source):** อัตรา fouling ปัจจุบันต้องมาจาก **รอบที่กำลังวิ่งจริง** (`cur_rid`) เท่านั้น — `Fouling_Rate_By_Run.csv` มีแถวต่อรอบก็ต่อเมื่อรอบนั้นสะสมวัน ≥29 วันหลังล้างแล้ว จึงเป็นไปได้ที่รอบปัจจุบันยังไม่มีแถว แล้วโค้ดเดิมหยิบแถวสุดท้ายในไฟล์ (รอบเก่าที่จบไปแล้ว) มาแสดงคู่กับ "critical/เลยเกณฑ์" ของรอบปัจจุบัน → ขัดแย้งกันเอง (พบจริงที่ E112C). แก้เป็น filter `Run==cur_rid` ก่อน, fallback เป็น fit ปลายรอบปัจจุบัน, สุดท้ายจึงใช้รอบก่อนหน้าพร้อม**ติดธง `rate_source='previous_completed_run'` และงดสรุปแนวโน้ม** (mirror `3b`).
- Q↔CIT: ใช้ `CIT_sensitivity_degC_per_Qnorm` (2c) → รายงาน Q-loss[kW] และ CIT-loss[°C] ทั้ง "ตอนนี้" และ "ที่เกณฑ์".

### 6.2 สัญญาณ degradation (ข้อ 6)
`end_of_run.json.signals` สรุปเป็นข้อความไทย: U_rel ลด/เดือน, ใกล้เกณฑ์กี่วัน, duty หาย %, คืน CIT ได้กี่°C,
ธง R² ต่ำ. `health ∈ {critical, warn, watch, ok}` ใช้ระบายสี badge.

### 6.3 Cleaning simulation (ข้อ 2)
Slider "ล้างในอีก N วัน" จำลอง CIT-loss(t) = L₀ + k·t (k จาก loss@เกณฑ์−loss ตอนนี้ ÷ วันถึงเกณฑ์),
reset ≈ 0 ณ วันล้าง แล้วโตใหม่ → พื้นที่ต่างสองเส้น = พลังงานที่ประหยัด, คิดเป็น ฿ สะสมถึง NEXT_TAM.
ออกแบบให้ **date-range agnostic** รองรับข้อมูลปี 2021–2026 เมื่อได้มา.

### 6.4 Furnace advisory (ข้อ 3)
`build_dashboard_topology.py` ใส่ `advice_hi/advice_lo` ต่อ constraint (O₂/draft/COT/skin/stack/CIT…).
เมื่อค่าออกนอก band → แสดงการ์ดคำแนะนำเฉพาะจุด. **limit + คำแนะนำ = ค่าสมมติ (`limits_assumed=true`) รอวิศวกรยืนยัน**.

### 6.5 รายการ cleaning/bypass/TAM (ข้อ 4)
`notebooks/cleaning_logistics.py` → `cleaning_logistics.json`: วิธีล้าง (จาก effort_tier), spare shell
(E113A↔E112C จาก config), last TAM (2024-06-14 จริง). **bypass มาจากไฟล์จริงของโรงงาน (`bypass_config.py`) —
ไม่ใช่ placeholder อีกต่อไป (แก้ 2026-07-12 ดู §12)**; เหลือแค่ next_TAM ที่ยังเป็น placeholder รอวิศวกร.

### 6.6 Hot-side + flow (ข้อ 5)
`export_hx_timeseries.py` เพิ่ม series `hot_in/hot_out/cold_flow/hot_flow` (จาก tags ใน cpht_features);
แท็บ HX รายตัวพล็อตสายร้อนและ flow เพื่อความโปร่งใสของตัวแปรที่ใช้คำนวณ effectiveness.

### 6.7 โมเดลความคุ้มค่า CIT→฿ (ข้อ 7)
`pipeline/export_economics.py` → `economics.json` (แหล่งเดียวให้เว็บ+รายงานตรงกัน). สมดุลพลังงานเตา (ตรวจหน่วยแล้ว):

| ปริมาณ | สูตร | หน่วย |
|---|---|---|
| เชื้อเพลิงที่ประหยัด | `charge·ρ·Cp·ΔCIT / (LHV·η)` | kg/h |
| มูลค่า/วัน | `fuel[t/h]·24·FG_PRICE` | ฿/วัน |
| คืนทุน | `CLEANING_COST / (฿/วัน)` | วัน |
| CO₂ ลด | `fuel[t/h]·24·CO2_FACTOR` | t/วัน |

**ค่าคงที่ — สถานะ (จริง/สมมติ):**

| ค่า | ค่าเริ่มต้น | สถานะ |
|---|---|---|
| Cp crude | 2.2 kJ/kg·K | สมมติ (เชิงเปรียบเทียบ) |
| ρ crude | 850 kg/m³ | สมมติ |
| LHV fuel gas | 48000 kJ/kg | สมมติ |
| η furnace | 0.88 | สมมติ |
| FG price | 18000 ฿/t | **สมมติ — รอวิศวกร** |
| Cleaning cost | 150k–400k ฿/ครั้ง (tier ตามวิธีล้าง) | **สมมติ — รอวิศวกร** (baseline ~100k-500k ตามช่วงจริงหน้างาน 2026-07-12; ปรับต่อ HX ได้บน dashboard) |
| CO₂ factor | 2.75 t/t FG | สมมติ |
| NEXT_TAM | 2028-06-01 | **placeholder — รอวิศวกร** |

ทุกค่าปรับได้บน dashboard (แท็บ Optimization) และติดป้าย "ค่าสมมติ" ชัดเจน. CIT gain ต่อ HX มาจาก 2d/6d
(single-TAM calibration) จึงเป็น **เชิงทิศทาง** จนกว่าจะมี TAM ที่สองมา validate.

### 6.8 ไฟล์ข้อมูลใหม่ (dashboard/data/)
`end_of_run.json` · `economics.json` · `cleaning_logistics.json` — สร้างโดย post-processors ใน `run_all.py`.

### 6.10 แท็บ "หลักฐาน & ความเชื่อมั่น" (Evidence & Confidence) — เพิ่ม 2026-07-12
`pipeline/export_evidence.py` → `evidence.json` (single source of truth, คำนวณจากข้อมูลต้นทางทุกครั้งที่รัน pipeline
จึงไม่ drift): รวมหลักฐานไว้ที่เดียวสำหรับเดโมกับวิศวกร —
- **Data provenance:** ช่วงข้อมูล, #วัน CIT, #HX, #รอบ fouling, #เหตุการณ์ล้าง audited, #TAM ที่ตรวจพบ (คำนวณจาก Fouling_Rate_By_Run.csv + cleaning_history.json).
- **Validation scorecard:** ตาราง CIT model (persistence vs XGB/RF/ablation/LSTM) พร้อม CV R² + verdict "ชนะ persistence ไหม", skill%, + fouling leave-HX-out R², quality gate (นับสด), degradation-driver CV.
- **ทะเบียนค่า วัดจริง/โมเดล/สมมติ:** จำแนกทุกปริมาณหลักพร้อมที่มา + สีกำกับสถานะ.
- **Caveats + live flags:** ข้อจำกัด (§3-4) + ธงที่คำนวณจากข้อมูลปัจจุบัน (เช่น HX ที่ rate มาจากรอบก่อนหน้า, past-trigger, R² ต่ำ) — แสดงตรง ๆ ไม่ซ่อน.

### 6.9 ประวัติการล้าง (Cleaning Audit History) — วัดจริง vs โมเดล
`pipeline/export_cleaning_history.py` → `cleaning_history.json`: ต่อ HX ดึงทุกเหตุการณ์ล้างที่เคยเกิด
(`{HX}_event_type` = SWITCH/TAM ที่ `days_on_duty` reset=0 ใน `Feature_calculated.csv`) แล้ววัด **จุดกระโดด (recovery)**:
- `U_recovered = U_relative[event] − U_relative[event−1]`, `Q_recovered = Q[event] − Q[event−1]` [kW].
- **CIT คืน (วัดจริง):** HX ปลายเทรนที่ cold_out = CIT tag (E113A/E112C) → ใช้ **cold_out jump ตรง**;
  ตัวอื่น → `ΔQ_recovered/charge × CIT_sensitivity` (2c), flag `gain_estimable=False` เมื่อ |Q_CIT_corr|<0.2 หรือ sensitivity≤0.
- **CIT คืน (โมเดล):** `expected_CIT_gain_C` (2d/6d) — แสดงเทียบข้าง ๆ ค่าวัดจริงเพื่อให้วิศวกรตรวจว่าโมเดลตรงกับของจริงแค่ไหน.
- แต่ละแถวผูกกับ **fouling rate ของรอบที่จบ** (run N−1 จาก `Fouling_Rate_By_Run.csv`: dUrel/เดือน, R², N, reliable)
  และปิดท้ายด้วยแถว **"คาดการณ์ครั้งถัดไป"** จาก `end_of_run.json`.
- Dashboard: ตาราง "ประวัติการล้าง" ในแท็บ HX รายตัว + **label เหตุการณ์บนกราฟ sawtooth** (TsChart `eventLabels`) +
  `<Basis>` แสดงเกณฑ์ครบ. หมายเหตุ: TAM ครั้งแรกมัก CIT-วัดจริงสูง (ทั้งเทรนสะอาดพร้อมกัน) ต่างจากค่าโมเดล (recoverable ปัจจุบัน) — เป็นข้อมูลให้วิศวกรพิจารณา.

## 7. ข้อมูล 2021-2026 + สูตรโรงงาน + แผนถึง TAM 2028 (เพิ่ม 2026-07-09)

### 7.1 ฐานข้อมูลขยาย 2021-01-01 → 2026-07-01
- ไฟล์ raw เดิม (`Process information data (2024-2026).xlsx`) ถูกแทนด้วยชุด 2021-2026 (layout เดิม — notebook 1 อ่านได้ทันที);
  crude assay (`Curde Property.xlsx`) ครอบ 2021 แล้ว (notebook 0 re-run).
- **TAM หลายรอบ**: `cpht_features.get_tam_dates()` อ่านจาก event ใน `Feature_calculated.csv` (ตรวจพบจริง **2021-03-25** และ **2024-06-14**);
  `get_clean_baseline_mask` = union ของทุก window หลัง TAM. `TAM_DATE` เดิมคงไว้เป็น fallback.

### 7.2 Bypass — ข้อมูลจริง + การแก้ข้อมูลช่วงล้าง
- `src/domain/bypass.py` (was `notebooks/bypass_config.py`) parse `list bypass Cleaning Heat Exchanger.xlsx` (ต่อ shell → รวมเป็นกลุ่ม HX):
  bypass จริงต่อตัว (เช่น E103AB/E106AB/E107AB/E109AB = TAM-only; E111 ใช้ tube-bypass ร่วมกับ 3E110C ตาม remark).
- **ตรวจพบว่า Operating_State เป็น NORMAL ตลอดช่วงล้าง-ผ่าน-bypass** (daily average + flow meter ร่วมมองไม่เห็น) →
  การวัด recovery ใน cleaning audit ใช้ **robust window**: ก่อน = median วัน [-5..-2], หลัง = median วัน [+1..+4]
  (เว้นวัน transition) แทนค่าแถวเดียว — ผล: 109 เหตุการณ์ audited ทั้ง 2021-2026.

### 7.3 โมเดล clean-Q เพิ่ม hot-side inlet (แก้ chart 3 ให้ถูกหลัก)
- `3a` feature_cols เพิ่ม **`hot_in`** (Q = UA·ΔT_lm — hot inlet เป็นตัวขับ duty หลัก; เดิม gap ปนเปื้อนจาก
  อุณหภูมิสายร้อนแกว่ง) → deviation สะท้อน fouling ตรงขึ้น.

### 7.4 เศรษฐศาสตร์ = สูตรโรงงานจริง (Energy Saving Benefit)
- `Saving[฿/ปี] = ΔCIT × 0.74 MMBTU/D/KBD/°C × Feed[KBD] × NG 390 ฿/MMBTU × 360 × 0.5 (decay factor)`;
  Feed[KBD] = charge×24/158.987. ตรวจซ้ำสไลด์: 2°C @80KBD = 8,311,680 ฿/ปี ✓.
- **ΔCIT ใช้ค่าวัดจริง** (median จาก audit) ก่อนเสมอ — ค่าโมเดล (2d/6d) over-estimate; แก้ไขแล้วด้วย **event-study
  calibration** (`export_economics.event_study_calibration`, 2026-07-13): ratio วัดจริง/โมเดล จากทุก clean event
  ที่มีทั้งสองค่า (32 events, 8/16 HX ณ ตอนนี้) ไม่ใช่แค่ TAM event เดียว (E113A) เหมือนเดิม — แยกกลุ่ม
  terminal-vs-non-terminal train position (ratio จริง ~0.23 vs ~0.39 ต่างกันพอสมควร) แล้วคูณ factor นี้กับค่าโมเดล
  fallback สำหรับ 8 HX ที่ยังไม่มีประวัติวัดจริงของตัวเอง แทนการใช้ค่าโมเดลดิบตรงๆ.
- สูตร LHV/η เดิมเก็บเป็น cross-check (`legacy_baht_day`) — ต่างกัน ~10-15%. ค่าล้างต่อ HX (`CLEANING_COST_BY_HX`) ยังเป็นค่าสมมติตาม tier.

### 7.5 TAM deep analysis (`08_tam_constraint_analysis.ipynb` → `tam_analysis.json`)
CIT เต็มช่วง + SOR/EOR ต่อรอบ E113A (กรอบเดียวกับสไลด์) + event-study ΔCIT ต่อการล้างทุกครั้ง (median ±10 วัน เว้น 2 วัน,
รายงาน Δcharge คู่กัน) + จุด CIT ตกแรงสุด พร้อม attribution ตาม U_relative ของ HX ในเครือข่าย + Rf(t) tracking.

### 7.6 แผนล้างถึง TAM 2028 (`pipeline/cleaning_scheduler.py` → `cleaning_schedule.json`)
- ต่อ HX: ช่วงล้างที่เหมาะสม **T\* = √(2C/(k·r))** (minimize ค่าพลังงานที่เสีย + ค่าล้าง; k = ฿/วัน/°C สูตรโรงงาน,
  r = ΔCIT วัดจริง ÷ median run duration) — closed-form โปร่งใส ตรวจมือได้ (เลือกแทน MILP ตามหลัก explainability-first).
- Constraint: ล้าง online ได้เฉพาะตัวที่มี bypass จริง; ที่เหลือรอ TAM 2028 (วันที่ TAM = placeholder).
- **เพดานความถี่ 4 ครั้ง/ปีต่อ HX** (`MAX_FREQ_PER_YEAR`, hard constraint — clip T* ที่ ≥ 365/4 วัน): ข้อจำกัดกำลังคน/logistics จริงหน้างาน (3-4 ครั้ง/ปีปกติ, 4 เฉพาะเหตุฉุกเฉิน) — กันไม่ให้สูตร T* แนะนำถี่เกินจริง. v2 (network) บังคับด้วย per-HX trailing-12-month clamp เช่นกัน.
- **หลัง 2028**: ทุกตัว reset ที่ TAM แล้ว extrapolate ความถี่เดิม 4 ปี.
- Dashboard (แท็บแผนล้าง): what-if CIT limit (ตั้ง limit → วันถึง + ฿ ที่เสียถ้าเดินต่ำกว่า/เลื่อนล้าง),
  กราฟ SOR/EOR สไตล์สไลด์, Gantt + ตารางความถี่.

## 8. Cleaning-Schedule Optimizer v2 — Network-Coupled Moving-Window (เพิ่ม 2026-07-10)

### 8.1 ทำไมต้องมี v2
v1 (`pipeline/cleaning_scheduler.py`) หา T* = √(2C/(k·r)) ต่อ HX **อิสระจากกัน** — โปร่งใส ตรวจมือได้ แต่มองข้าม
ปฏิสัมพันธ์ข้าม HX (ล้างตัวหนึ่งกระทบอุณหภูมิขาเข้าตัวถัดไปในสาย, งบ/กำลังคนล้างจำกัดต่อเดือน) การทบทวนวรรณกรรม
(ดู §9 ภาคผนวก) พบเปเปอร์ที่ตรงประเด็นนี้โดยตรง: **Dekebo, S.B.; Oh, G.-T.; Lee, M.-W. "Cleaning Schedule
Optimization of Heat Exchanger Network Using Moving Window Decision-Making Algorithm." Appl. Sci. 2023, 13, 604**
(ต่อยอดจาก Al Ismaili, Lee, Wilson, Vassiliadis, *Comput. Chem. Eng.* 2018, 111, 1-15) — พบว่าการแก้ปัญหาทั้ง horizon
เดียว (fixed-horizon OCP) ล้มเหลวไม่ลู่เข้า bang-bang เมื่อ horizon ยาวเกิน ~30 เดือน แต่วิธี **moving window**
(แก้ทีละหน้าต่างเล็ก เลื่อนไปเรื่อย ๆ) ยังคงได้ผลลัพธ์ใกล้เคียง optimal และเร็วกว่ามาก — horizon ของเราไป TAM 2028
(~24 เดือน) อยู่ตรงจุดที่วิธีนี้เริ่มมีประโยชน์จริง

### 8.2 ทำไมไม่ทำตามเปเปอร์ทุกตัวอักษร (ข้อจำกัดที่บันทึกไว้)
เปเปอร์จำลองเครือข่ายด้วย ε-NTU DAE เต็มรูป (Eq. 1-9): ผูก T_cold_out/T_hot_out ของแต่ละ HX ต่อกันเป็นสาย โดยต้องรู้
`α = UA/(Fh·Cph)` ต่อ HX ซึ่งต้องการ **UA/พื้นที่ผิวจริง**. ข้อมูลนี้**มีอยู่จริง** (`Data\Data Sheet Heat Exchanger.xlsx`
มี Surf./Shell, U-clean/U-service, Rf design ต่อ shell ทุกตัว) **แต่เป็นค่า design ตอนสร้างเครื่อง** — โปรเจกต์นี้พิสูจน์
มาแล้วหลายจุดว่า U_clean จริงที่วัดได้ต่อรอบ (`U_clean_run` ใน Fouling_Rate_By_Run.csv) ต่างจาก nameplate เสมอ
การเอา UA design มาจำลอง DAE ทั้งเครือข่ายโดยไม่ validate ก่อนจะขัดกับหลักการ "ไม่ overclaim" ที่ยึดมาตลอด (เช่น
CIT persistence finding) จึงเลือกใช้ **reduced-form coupling**: ผลรวมอัตราการเสีย CIT ที่**วัดจริง**ต่อ HX (r_hx,
°C/วัน — ตัวเดียวกับที่ v1 ใช้คำนวณ T*, มาจาก cleaning_history.json) แทนการจำลองอุณหภูมิไหลผ่านทีละ HX — เพราะ r_hx
ถูก fit กับ CIT จริงอยู่แล้ว จึงซ่อนผลกระทบข้ามสายที่เกิดขึ้นจริงไว้ในตัวมันเองโดยไม่ต้องสมมติ UA nameplate เก็บ
UA design ไว้เป็นตัวเลือก cross-check ในอนาคตเท่านั้น (future work หากต้องการจำลอง DAE เต็มรูปแบบ ต้อง validate UA
design เทียบ U_clean_run ที่วัดได้ก่อน)

### 8.3 สูตร (`pipeline/cleaning_scheduler_network.py`)
- **State ต่อ HX:** `deviation_hx(t)` (หน่วย °C-equivalent) โตเชิงเส้นด้วย r_hx ต่อเดือน (30 วัน), รีเซ็ตเป็น 0 เมื่อล้าง
- **Objective ต่อ window** (ปรับจาก Eq. 10 ของเปเปอร์ ใช้สูตรพลังงานโรงงานแทน CE/η_f):
  `Obj = Σ_t [k×30×CIT_deficit_total(t)] + Σ_hx Σ_t Ccost_hx×y[hx,t]` โดย `k = STD_ENERGY×Feed_KBD×NG_PRICE`
  (สูตรเดียวกับ v1/economics.json), `CIT_deficit_total(t) = Σ_hx deviation_hx(t)`, `y[hx,t]∈[0,1]` ผ่อนเป็น continuous
  (1 = ล้างงวดนั้น) แก้ด้วย `scipy.optimize.minimize(method='SLSQP')`
- **Moving-window:** ทดลองขนาดหน้าต่าง [2,3,4,5,6] เดือน (ตาม Fig.3/Table 2 ของเปเปอร์), แต่ละขนาดแก้ปัญหาทั้ง horizon
  ด้วยการเลื่อนหน้าต่างทีละ 1 เดือน (แก้ทั้งหน้าต่าง, commit เฉพาะเดือนแรก แล้วปัด bang-bang), เลือกขนาดที่ realized
  cost ต่ำสุด — ผลตรงกับทิศทางที่เปเปอร์รายงาน: หน้าต่างเล็กเกินไปทำให้ล้างน้อยเกิน (มองเห็นความเสียหายในหน้าต่างน้อยเกิน
  จนดูเหมือนค่าล้างแพงกว่าน้ำมันเชื้อเพลิงที่ประหยัดได้เสมอ), หน้าต่างใหญ่เกินไปทำให้ล้างถี่เกินจำเป็น
- **Constraint:** `MAX_ONLINE_CLEANS_PER_PERIOD` (ค่าสมมติ default=2 ตัว/เดือน จำกัดกำลังทีมล้าง — รอวิศวกรยืนยัน)
  บังคับผ่าน LinearConstraint; เฉพาะ HX ที่มี bypass จริง (bypass_config) เป็น decision variable ตัวอื่นรอ TAM เหมือน v1
- **Honest v1-vs-v2 comparison:** rebuild ตาราง cleaning ของ v1 เป็น y-matrix แล้วให้ objective function เดียวกับ v2
  ประเมิน (`realized_cost`) — เทียบกันตรง ๆ ไม่ใช่คนละหน่วย, รายงานผลตามจริงแม้ v2 จะไม่ดีกว่า v1 (ผลจริงที่ได้: v2
  ประหยัดกว่า v1 **~14%** สำหรับข้อมูลชุดนี้ที่ค่าล้าง baseline ใหม่ + เพดาน 4 ครั้ง/ปี — ตัวเลขจะเปลี่ยนเมื่อรันซ้ำกับข้อมูล/ค่าล้างใหม่)

### 8.4 Dashboard
แท็บ "แผนล้าง HX" มีทั้ง v1 (`SchedulePanel`, independent T*, ค่า default) และ v2 (`NetworkSchedulePanel`, network-coupled,
มุมมองเสริม) พร้อมกล่องเทียบต้นทุนรวมและ Basis อธิบายวิธี+ข้อจำกัด — v1 ยังเป็นค่า default เพราะอธิบายง่ายกว่าและ
พิสูจน์แล้วก่อน v2 ตามหลัก explainability-first ของโปรเจกต์

### 8.5 Solver comparison — SLSQP relaxation vs mixed-integer (2026-07-13)
v2 แก้ `y[hx,t]∈{0,1}` แบบ continuous relaxation (SLSQP) แล้ว round — ไม่รับประกันว่าเป็น optimum ของปัญหา integer
จริง `pipeline/solver_comparison.py` + `_diagnostic_solver_comparison.ipynb` (ชื่อเดิม `16b_optimizer_solver_comparison.ipynb`)
เทียบ window เดียวกันทุกประการด้วย
`scipy.optimize.differential_evolution(integrality=True)` (mixed-integer global search แบบไม่ต้องติดตั้งอะไรเพิ่ม
— ไม่ใช่ Pyomo+Bonmin/Couenne เต็มรูปที่มี optimality-gap certificate ซึ่งหนักเกินไปสำหรับ dependency policy ของ
โปรเจกต์นี้) และ GA เล็กๆ (dependency-free) **ผลจริงจากการรันครั้งแรก**: หน้าต่าง 2 เดือน ทั้งสามวิธีเท่ากัน, หน้าต่าง
4 เดือน DE เจอคำตอบที่ดีกว่า SLSQP+round **3.19%**, หน้าต่าง 6 เดือน SLSQP กลับดีกว่า DE (DE แพ้ ~11%, น่าจะเพราะ
`maxiter`/`popsize` ไม่พอสำหรับมิติที่ใหญ่ขึ้น ไม่ใช่ว่า SLSQP เก่งกว่าเชิงโครงสร้าง) — ผลไม่ชี้ขาดพอที่จะเปลี่ยน
production solver ทันที (gap ที่เจอ <3-3.5% อยู่ในเกณฑ์ "close enough" ที่วางแผนไว้) แต่ยืนยันว่า SLSQP+round
*อาจ* ทิ้ง saving เล็กน้อยไว้บนโต๊ะในบางกรณี ควรรัน notebook นี้ซ้ำเป็นระยะ (ไม่ใช่ production step, ไม่ได้ผูกกับ
`run_all.py`) เพื่อติดตาม ไม่ใช่รันทุกครั้งที่กดปุ่ม "คำนวณใหม่" บนแดชบอร์ด (DE/GA ช้ากว่า SLSQP มาก — ดูตัวเลขเวลาใน
notebook)

## 9. ภาคผนวก: รีวิววรรณกรรม 11 ฉบับ (`เอกสารงานวิจัย\`, ทบทวน 2026-07-10)

พี่วิศวกรขอให้พิจารณางานวิจัย 12 ไฟล์ (มี 1 ไฟล์ซ้ำ: `applsci-13-00604-v2.pdf` = `Cleaning_Schedule_Optimization_of_
Heat_Exchanger_N.pdf` เปเปอร์เดียวกัน) เทียบกับระบบที่มีอยู่ สรุปเป็น 3 กลุ่มตามความคุ้มค่า/effort:

| # | เปเปอร์ (ผู้แต่ง, ปี) | ใจความ | สถานะ/relevance |
|---|---|---|---|
| B1 | Dekebo, Oh & Lee, *Appl. Sci.* 2023 | Moving-window OCP joint scheduling ทั้งเครือข่าย | **ทำแล้ว → v2 (§8)** |
| A1 | Al Ismaili et al., *Comput. Chem. Eng.* 2019 | Uncertainty propagation (P10/P50/P90) บนพารามิเตอร์ fouling/cleaning | ยังไม่ทำ — MEDIUM-HIGH, reuse Monte-Carlo ใน phm_analysis.py ได้ทันที (แนะนำทำต่อ) |
| A2 | Ujevic Andrijic & Rimac, *Sensors* 2025 | Clean-baseline LSTM/XGBoost + CO₂/carbon-price economics | ยืนยัน design เดิม (clean-baseline model, distrust tree extrapolation); CO₂-equivalent metric ยังไม่เพิ่ม — cheap add-on |
| A3 | Hosseini et al., *Energy Reports* 2022 | √Rf target transform, Bland-Altman diagnostic | ยังไม่ทำ — cheap, ทดลองได้ใน notebook 2b/3a |
| C1 | Wilson, Ishiyama & Polley (review), 2015 | Ebert-Panchal threshold fouling model (deposition-vs-shear kinetics) | ไม่ทำ — ต้องการ wall-shear/film-temp ที่ไม่มี, งานวิจัยเองบอกว่า plateaued |
| C2 | Rodriguez & Smith, *Trans IChemE* 2007 | Proactive bypass-as-fouling-suppression (ลด wall temp ด้วย bypass) | ไม่ทำ — ต้อง fit Ebert-Panchal parameters ก่อน, medium effort สูง |
| C3 | Togun et al. (review), *Int. Comm. Heat Mass Transf.* 2025 | สำรวจ ML ใน HX (PINN, XAI, federated learning) | LOW — ระบบเข้มงวดกว่า median literature อยู่แล้ว (walk-forward CV ไม่มีในรีวิวนี้ด้วยซ้ำ) |
| B2 | Biyanto et al. (PSO), ASTECHNOVA 2014 | PSO scheduling ทั้งเครือข่าย, Kern-Seaton model | LOW-MEDIUM — v1/v2 ครอบคลุมแล้วด้วยวิธีโปร่งใสกว่า |
| B3 | Lozano Santamaria, Honein & Macchietto, ESCAPE30 2020 | Joint retrofit (เพิ่ม/ขยาย HX) + cleaning schedule | ไม่ทำ — นอก scope (capex/topology decision ไม่ใช่ monitoring tool) |
| B4 | Tian, Wang & Feng, *Energy* 2016 | Joint flow-velocity + cleaning optimization (Polley threshold) | ไม่ทำ — ต้องการ velocity/geometry data ที่ยังไม่ยืนยันว่ามี |

**สรุป:** เลือกทำ B1 (network scheduler v2, §8) ก่อนตามที่ตกลง; A1/A2/A3 เป็นตัวเลือก low-effort สำหรับรอบถัดไป;
C1-C3, B2-B4 บันทึกไว้เป็นข้อเสนอแนะอนาคต ไม่ใช่งานที่ควรทำตอนนี้ (ข้อมูล/ขอบเขตไม่พร้อม หรือระบบมีวิธีที่ดีกว่าอยู่แล้ว)

## 10. การแก้ไขเพื่อความถูกต้อง (correction log, 2026-07-12)

รอบทบทวนตามคำขอฝ่ายวิศวกรรม — แก้ 3 จุดที่กระทบตัวเลขบน dashboard โดยตรง พร้อมเหตุผลเชิงวิศวกรรม:

1. **ค่าล้าง HX ลดจาก 0.8–2.0M เป็น baseline 150k–400k ฿/ครั้ง** (`export_economics.py::CLEANING_COST_BY_HX`).
   เดิมสมมติสูงเกินช่วงจริงหน้างาน (~100k-500k) ทำให้ T* = √(2C/kr) ยืดยาวเกินจริงและบิดเบือน net-saving.
   Tier ใหม่: สลับเชลล์ (E113A/E112C) 150k < online-bundle 300k < TAM-scope 400k. **ปรับต่อ HX ได้บน dashboard**
   (เก็บใน localStorage, คำนวณ T*/ครั้งต่อปี/net-saving สดด้วยสูตรเดียวกับ pipeline).

2. **เพดานความถี่ล้าง 4 ครั้ง/ปีต่อ HX เป็น hard constraint** (v1 clip T*≥365/4; v2 per-HX trailing-12-month clamp).
   เดิม E113A/E102 ได้ 6.08 ครั้ง/ปี เกินกำลังคน/logistics จริง (ปกติ 3-4, 4 เฉพาะฉุกเฉิน). ดู §7.6.

3. **แก้ misclassification "เลยเกณฑ์" + "แนวโน้มไม่แย่ลง" พร้อมกัน (E112C)** — rate ค้างจากรอบเก่า.
   เพิ่ม `rate_source` guard ใน `export_end_of_run.py` (ดู §6.1). E113A ไม่กระทบ (รอบปัจจุบัน = แถวล่าสุดพอดี)
   แต่เป็น latent risk เดียวกันเมื่อสลับเชลล์/ล้างครั้งหน้า — จึงแก้ที่ต้นเหตุ ไม่ใช่เฉพาะ E112C.

**ที่ตรวจแล้วว่าไม่ใช่บั๊ก (ไม่แก้):** `worsening` (2d, run-over-run rate acceleration) เป็นคนละแกนกับ raw negative rate —
เป็น design ตั้งใจ (ดู §3D); slide-check เศรษฐศาสตร์ยัง reproduce 8,311,680 ฿/ปี หลังเปลี่ยนค่าล้าง (ค่าล้างไม่อยู่ในสูตร slide).

4. **ยกเครื่องการคำนวณ fouling rate ใหม่ทั้งหมด (robust, physically-constrained)** — ดู §11.
   เดิม OLS-ต่อรอบบน U_relative ให้ผลขัดฟิสิกส์ (17/96 รอบ slope เป็นบวก, throughput confound, ไม่กรอง state, ไม่ segment ล้าง).

## 11. Robust fouling-rate methodology (2026-07-12) — `nb_audit.robust_fouling_rate` + `pipeline/compute_fouling_rate.py`

**ปัญหาเดิม (ยืนยันด้วยข้อมูล):** `02_feature_engineering.ipynb` fit OLS เชิงเส้นต่อรอบบน U_relative ตรง ๆ →
17/96 รอบมี slope เป็นบวก (U เพิ่ม = ตรงข้าม fouling), R² ต่ำ (median 0.20), บางรอบเป็น throughput confound จริง
(E109AB Run1: corr(U_rel, flow)=+0.91), baseline U_clean_run เพี้ยนจน U_relative ทะลุเพดาน clip 2.0, ไม่กรอง
operating state (E112C Run11/13 เป็นช่วง SUBSTITUTED ล้วน), และ regression พาดข้ามเหตุการณ์ล้างกลางรอบ.

**วิธีใหม่ (ต่อรอบ, robust):**
- **In-service mask** — ใช้เฉพาะ state ∈ {NORMAL, SUBSTITUTE_ACTIVE, PARALLEL} จาก `Operating_State.csv`
  (ตัดช่วง OFF/SUBSTITUTED/BYPASS/CLEANING ที่ HX ไม่ได้ถ่ายเทความร้อนจริง). ทำให้ E112C วัด rate ได้เฉพาะตอน
  substitute-active จริง แทนที่จะมั่วจากช่วงที่ปิดอยู่.
- **Winsorize** U_relative ที่เพดาน 1.10 — ค่าที่สูงกว่านี้เป็น artifact จาก baseline ต่ำ/throughput ไม่ใช่ "สะอาดกว่าสะอาด".
- **Theil-Sen** (median ของ slope คู่, breakdown ~29%) แทน OLS + คืน 95% CI — ทนต่อ spike ที่ OLS แพ้.
- **Rf cross-check** — fit dRf/dt (fouling resistance, ต้อง ≥0 เชิงฟิสิกส์) เป็นตัวตรวจ sign-consistency.
- **Recent-window rate** (60 วันท้าย) = อัตรา "ปัจจุบัน" สำหรับ monitoring (whole-run slope อ่านต่ำในรอบยาว/asymptotic).
- **Intra-run split** — ถ้า U_relative กระโดดขึ้นกลางรอบ (ล้างที่ไม่ถูกตรวจจับ) ตัดใช้เฉพาะ segment หลัง recovery ล่าสุด.
- **Reliability gate + physical constraint** — รอบจะ `reliable` ก็ต่อเมื่อ span ≥30 วัน, ≥20 จุด, in-service ≥50%,
  Theil slope **< 0** และ CI upper < tol, และ Rf สอดคล้อง; ไม่งั้นติดธง `rate_flag` (positive_slope_throughput /
  flat_no_signal / insufficient_span / substituted_dominated / rf_inconsistent) แล้ว **null ค่า rate หลัก**
  → downstream ที่ dropna (2d) ตัดออกอัตโนมัติ, ไม่มีตัวเลข unphysical เข้า ranking/scheduler.

**Invariant ที่บังคับ+assert:** ไม่มีรอบ `reliable` ที่ slope ≥ 0. ผลจริง: 69/125 รอบ reliable (ทุก HX มี ≥2 รอบ
รวม E112C), อัตรา reliable อยู่ช่วง −0.27..−0.002 /เดือน (ลบทั้งหมด สมเหตุสมผล).

**Dependency:** ต้องรัน *หลัง* 2a (ต้องใช้ `Operating_State.csv`) — จึงอยู่ใน `pipeline/compute_fouling_rate.py`
ที่ `run_all.py` เรียกทันทีหลัง 2a และเขียนทับ `Fouling_Rate_By_Run.csv` ที่ notebook 2 เขียนไว้แบบหยาบ.
**ข้อจำกัดที่เหลือ:** baseline U_clean_run ยังเป็น P90-30วันแรก (winsorize ชดเชยด้าน rate); flow เป็น confound ที่
ยอมรับไว้ (ไม่ทำ full flow-normalization — ดู §4).

## 12. แก้ "วิธีการล้าง" ให้อ้างอิงไฟล์ bypass จริง + ล้างบางส่วน + คำนวณใหม่สด (correction, 2026-07-12)

**ปัญหาที่พบ (คำขอวิศวกร: "ต้องอ้างอิง list bypass Cleaning Heat Exchanger"):** `cleaning_method`/`online_capable`
ที่แสดงบนแดชบอร์ดและใช้จัดตารางล้าง **ไม่ได้มาจากไฟล์ `list bypass Cleaning Heat Exchanger.xlsx` เลย** — มาจากลิสต์
`SWAP_CAPABLE`/`TAM_ONLY` ที่เขียนมือซ้ำกัน 2 จุด (`06_cleaning_priority_ranking.ipynb`, `07b_time_to_clean_prediction.ipynb`)
ซึ่ง**ขัดกับไฟล์จริงตรง ๆ**:

| HX | ไฟล์ bypass จริง | ลิสต์เขียนมือ (เดิม) | ผล |
|---|---|---|---|
| E101AB, E105AB | มี bypass (shared) | `TAM_ONLY` | เว็บบอกล้าง online ไม่ได้ ทั้งที่มี bypass |
| E103AB, E106AB, E107AB, E109AB | **ไม่มี bypass** (TAM) | `ONLINE_CLEAN_DEMONSTRATED` | จัดให้ล้าง online ทั้งที่ไฟล์บอกไม่มี bypass |
| E101CD | มี bypass **บางส่วน** (shell C ไม่มี, shell D มี) | `TAM_ONLY` (ปัดทิ้งทั้งกลุ่ม) | เสียโอกาสประหยัดจริงจาก shell D |

**แก้:**
1. **`bypass_config.py` เป็น single source of truth** — เพิ่ม `online_mode` ต่อกลุ่ม: `full` (bypass ร่วมทั้งกลุ่ม
   หรือทุก shell bypass ได้เอง), `partial` (บาง shell เท่านั้น เช่น E101CD → `duty_fraction=0.5`), `none` (ไม่มีเลย).
2. **Retire ลิสต์เขียนมือทั้ง 2 จุด** ใน 2d/3b ให้ import `BYPASS_CONFIG` แทน (SWAP_CAPABLE ยังคงมาจาก
   `cpht_config.PARALLEL_SHELL_GROUPS` ซึ่งเป็นคนละแนวคิด — spare-shell ไม่ใช่ bypass).
3. **`cleaning_logistics.py`** derive `cleaning_method`/`online_capable`/`effort_tier`/`duty_fraction` จาก
   `BYPASS_CONFIG` ทั้งหมด (เดิมอ่านจาก `Time_To_Clean_Prediction.csv`'s hardcoded tier).
4. **Partial-online scaling** — `cleaning_scheduler.py`/`cleaning_scheduler_network.py` คูณ ΔCIT ที่คืนได้ด้วย
   `duty_fraction` สำหรับกลุ่มที่ล้าง online ได้บางส่วน (ล้าง shell เดียวคืนได้ไม่เต็ม ไม่ใช่สมมติเต็ม).
5. **`worth_it` — เทียบ CIT ตรงกับเชื้อเพลิงเตา:** notebook 8 เพิ่ม `fuel_value_per_clean_thb` (มูลค่าเชื้อเพลิงเตาที่
   ประหยัดได้ต่อรอบล้าง จากสูตรพลังงานโรงงานเดียวกับ §7.4) เทียบตรงกับค่าล้าง → ตอบคำถาม "คุ้มไหม" ชัดเจน ไม่ใช่แค่ net-saving เชิงทฤษฎี.
6. **คำนวณใหม่จริง ไม่ใช่ประมาณ** — `cleaning_scheduler_network.py` แยกฟังก์ชัน `compute_schedule()` ให้ notebook 8
   เรียกสดพร้อม cost override (จาก `dashboard/data/cost_overrides.json`) แทนการโหลดไฟล์ static — ปุ่ม "คำนวณใหม่"
   บนแดชบอร์ด POST ไป `backend/server.py:/api/recompute-plan` ซึ่งเขียน override แล้วรัน notebook 8 จริง (~10-20 วิ)
   แล้วคืนแผนใหม่ทั้งหมด (ตาราง/ลำดับ/worth_it เปลี่ยนจริงตามค่าล้างที่แก้ ไม่ใช่แค่ปรับตัวเลขหน้าเว็บ).

**ผลลัพธ์หลังแก้ (ยืนยันด้วยการรัน):** E101CD กลับมาเป็น "ล้าง online ได้บางส่วน (50%)" แทนที่จะถูกปัดทิ้งเป็น TAM-only;
E103AB/E106AB/E107AB/E109AB ถูกต้องเป็น TAM-only ตามไฟล์จริง; total net saving ~118M ฿/ปี, 12 HX ล้าง online ได้
(1 บางส่วน), 5 TAM-only — ตัวเลขจะเปลี่ยนตามค่าล้างจริงที่วิศวกรกรอกผ่านปุ่ม "คำนวณใหม่".
