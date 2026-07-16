# Business Problem & Requirements — CPHT Fouling / CIT Optimization

Status: **DRAFT v2 — รวมเนื้อหาจาก `Business Problem Analysis and Requirements.docx` เข้ากับสถานะโค้ดจริงปัจจุบัน**

**ความสัมพันธ์กับเอกสารอื่น:**
- `Business Problem Analysis and Requirements.docx` (ในโฟลเดอร์เดียวกัน) คือ **spec ฉบับสมบูรณ์ที่สุดที่มีอยู่** — เขียนละเอียด
  ระดับ ID ต่อ requirement (BP-xxx, BO-xxx, FR-xxx, NFR-xxx, BR-xxx, AL-xxx, OI-xxx) ครอบคลุม Business Problem,
  Requirement Specification, Data Dictionary Template, API spec, Acceptance Criteria (Given-When-Then), Traceability
  Matrix และ Open Issues — **ไฟล์นี้ไม่ก็อปทุกบรรทัดมาซ้ำ** แต่สรุปโครงสร้าง + เติม "สถานะการพัฒนาจริง" กำกับแต่ละหัวข้อ
  ว่าโค้ดปัจจุบันทำถึงไหนแล้วเทียบกับ spec นี้ — **เปิด docx ควบคู่เวลาอ่านไฟล์นี้**
- `docs/02_Requirement_v2_SSOT.md` — engineering spec (HX layout, canonical Q/fouling method) ไม่ทับซ้อนกับไฟล์นี้
- `docs/ANALYSIS_PIPELINE_GUIDE.md` — pipeline ที่รันจริงตอนนี้ (27 ขั้นตอน)

---

## 0. ภาพรวมความสัมพันธ์ Spec vs. ของจริง (สรุปสั้นก่อนอ่านรายละเอียด)

docx เป็น **spec แบบ green-field** (เขียนราวกับเริ่มจากศูนย์) ในขณะที่ระบบจริงพัฒนาไปไกลแล้วในบางด้านและยังไม่แตะเลย
ในบางด้าน ภาพรวมคร่าว ๆ ก่อนลงรายละเอียด:

| กลุ่ม | สถานะเทียบ spec |
|---|---|
| การคำนวณ Q, Fouling, CIT Deficit, Ranking (FR-HX, FR-CB, FR-FU, FR-PR) | ✅ **มีแล้วและละเอียดกว่า spec ในหลายจุด** (เช่น Theil-Sen robust rate, SHAP attribution) |
| Cleaning Event Detection (FR-CL) | ⚠️ **บางส่วน** — อนุมานจากพฤติกรรมข้อมูล แต่ยังไม่มี UI ให้ engineer กด Confirm/Reject (FR-CL-007/008/009) |
| Web Dashboard (หัวข้อ 8 ของ docx) | ⚠️ **บางส่วน** — มี Overview/HX Detail/Furnace/Forecast/Plan/Model/Evidence (7 แท็บ)
  **ไม่ทำหน้า Login ตอนนี้** (ตัด scope แล้ว 2026-07-16 — ระบบเปิดดูได้ทุกคน ไม่ต้อง auth), ไม่มี Scenario Analysis แบบ
  interactive เต็มรูปแบบ (มี what-if ใน optimizer แต่ไม่ใช่หน้าเดียวกับที่ spec อธิบาย) |
| Business Rules (BR-001 ถึง BR-018) | ⚠️ **บางส่วน** — กฎสำคัญอย่าง "ห้ามแนะนำ Online Cleaning สำหรับ TAM_ONLY" (BR-001) และ "E101G ต้องระบุว่า
  Inferred" (BR-002) มีอยู่แล้วในโค้ด ส่วนกฎเรื่อง Role/Approval (BR-013) **ไม่ทำตอนนี้** เพราะไม่มี login/role — เก็บไว้เป็น backlog |
| Alert Requirements (AL-001 ถึง AL-015) | 📋 **Backlog (Won't Have Now)** — ระบบปัจจุบันเป็น dashboard แบบเปิดดู ไม่มีช่องทาง push notification ให้ใครอยู่แล้ว
  (ไม่มี login = ไม่รู้จะส่งหาใคร) — รายการ requirement ยังมีประโยชน์เก็บไว้อ้างอิงตอนจะทำจริงในอนาคต |
| User Roles & Permissions (หัวข้อ 6, RL-001 ถึง RL-007) | 📋 **Backlog (Won't Have Now) — ตัดออกจาก scope ตอนนี้ตามที่ยืนยัน 2026-07-16** ไม่ทำ login/RBAC เฟสนี้
  ทุกคนเห็นข้อมูลชุดเดียวกันหมด (เหมือนระบบปัจจุบัน) — เก็บ role/permission matrix ของ docx ไว้เป็นแบบร่างสำหรับตอนขยายระบบ |
| API Requirements (หัวข้อ 12, API-001 ถึง API-014) | 📋 **Backlog** — `backend/server.py` มี endpoint อัปโหลด Excel + สั่งรัน pipeline เท่านั้น ไม่ใช่ REST API ตาม spec
  ไม่เร่งด่วนเพราะ endpoint ส่วนใหญ่ใน spec (config/limits PUT, audit-log) ผูกกับ RBAC ที่ยังไม่ทำอยู่ดี |
| Data Dictionary Template (หัวข้อ 11) | ❌ **ยังไม่มีเป็นทางการ** — ข้อมูล tag mapping กระจายอยู่ใน `cpht_config.py` แต่ไม่มีฟิลด์ครบตาม template (ไม่มี valid min/max, warning/critical band ต่อ tag) — **ยังควรทำ** ไม่ผูกกับเรื่อง login |
| Non-functional (NFR-001 ถึง NFR-017) | ⚠️ **บางส่วน** — Reproducibility/Traceability ทำได้ระดับหนึ่ง (backup อัตโนมัติ, evidence.json) แต่ไม่มี audit log,
  ไม่มี pipeline failure notification — RBAC (NFR-003) ตัดออกจาก scope ตอนนี้ตามข้างต้น |
| Open Issues (OI-001 ถึง OI-020) | ยังเปิดเกือบทั้งหมด — ดู §5 ด้านล่าง ที่รวมกับ open items ของการสนทนานี้แล้ว |

---

## 1. Business Problem

### 1.1 บทสรุปผู้บริหาร (จาก docx §1, คงเนื้อหาเดิม)
โรงกลั่นบางจาก Plant 3 ใช้ **Crude Preheat Train (CPHT)** ถ่ายเทความร้อนจากกระแสร้อนในกระบวนการมาอุ่นน้ำมันดิบก่อนเข้าเตา
F101 มี HX รวม 16 ตัว แบ่งเป็น CPHT-1 (ก่อน Desalter) และ CPHT-2 (ก่อนเข้าเตา) เมื่อ HX เกิด **fouling** ความสามารถกู้คืน
พลังงานลดลง **CIT** จึงตกลงเรื่อย ๆ ตามเวลาใช้งาน ทำให้เตา F101 ต้องเพิ่มการเผา **Fuel Gas** เพื่อรักษา **COT** ที่เป้าหมาย
ผลกระทบไม่ได้จำกัดที่ต้นทุนเชื้อเพลิงเท่านั้น แต่ยังเพิ่ม **Tube-skin Temperature** ลด **Safety Margin** ก่อนเข้าสู่ระดับเสี่ยง
**Coking**/**Creep**

**ปัญหาทางธุรกิจที่แท้จริง:** โรงงานยังไม่มีระบบประเมินต่อเนื่องว่า fouling ของ HX แต่ละตัวทำให้สูญเสียการกู้คืนพลังงาน
เท่าใด กระทบ CIT/Fuel Gas/Operating Headroom ของเตาเท่าใด และไม่สามารถระบุได้มั่นใจว่าควรล้าง HX ตัวใด เมื่อใด ด้วย
ลำดับความสำคัญอย่างไร ภายใต้ข้อจำกัดเดินเครื่องจริง

**หมายเหตุสำคัญจาก docx (ยืนยันแล้ว ไม่ต้องถามซ้ำ):** ในระยะแรกระบบเป็น **Decision Support System เท่านั้น** ไม่สั่งการ/
เขียน setpoint กลับ DCS โดยอัตโนมัติ (`DCS Integration: Read-only`, `Automatic Control: ไม่อยู่ในขอบเขตระยะแรก`)

### 1.2 กลไกของปัญหา (จาก docx §3 — วงจรเสริมแรง)
```
HX Fouling → CPHT Heat Recovery ลดลง → CIT ลดลง → Furnace Duty เพิ่มขึ้น
   → Fuel Gas Flow เพิ่มขึ้น → Tube-skin Temperature เพิ่มขึ้น
   → Coking/Creep Risk เพิ่มขึ้น → Operating Headroom ลดลง
```
สมการหลัก: `Q_Furnace = ṁ_crude · Cp · (COT − CIT)` — เมื่อ CIT ลดลงโดย Crude Rate/COT target คงเดิม Furnace Duty
ต้องเพิ่มขึ้น **ข้อควรระวังสำคัญที่ docx ย้ำ (§3.2):** Q หรืออุณหภูมิที่ลดลง **ไม่สามารถสรุปตรงว่าเกิดจาก fouling** เพราะ
ขึ้นกับ Crude Flow/Assay, Hot-stream Condition, Configuration, Bypass Status ด้วย — ต้อง normalize เทียบ
"expected-clean performance" ก่อนเสมอ **[✅ โค้ดปัจจุบันทำถูกต้องตามหลักนี้แล้ว — ดู `pipeline/compute_fouling_rate.py`]**

### 1.3 เป้าหมาย / ผลลัพธ์ / ผู้ใช้งาน (สรุปรวมจาก docx + สิ่งที่ยืนยันในการสนทนานี้)

| หัวข้อ | คำตอบ | สถานะ |
|---|---|---|
| เป้าหมาย | ลดการใช้เชื้อเพลิงเตา F101 ผ่านการจัดลำดับ+กำหนดเวลาล้าง HX สาย CPHT โดยไม่ทำให้ tube-skin/coking risk เกินขอบเขต | ✅ |
| ทำนายอะไร | Q Loss/Fouling Rate ต่อ HX, CIT Deficit, Fuel Gas Penalty, Tube-skin Headroom, ΔCIT what-if | ✅ (docx ให้รายละเอียดกว่าที่ร่างไว้เดิมมาก — ดู BO-001 ถึง BO-009) |
| ผลลัพธ์ใช้ตัดสินใจ | ล้าง HX ตัวไหนก่อน/เมื่อไหร่ (online vs TAM), เมื่อไหร่ต้องลด Crude Rate | ✅ |
| ผู้ใช้งาน | **docx ระบุละเอียดกว่าที่คุยกันไว้มาก — 10 กลุ่ม** (§7.1): Process/Energy/Operation Engineer, Control Room Operator, Furnace Specialist, Maintenance Planner, Inspection Engineer, Reliability Engineer, Data Engineer, Data Scientist — ครอบคลุม 3 กลุ่มที่ยืนยันไว้ก่อนหน้า (วิศวกร, ผู้จัดการ/TAM planner, operator) แล้วเพิ่มกลุ่มเทคนิค (Data Eng/Scientist) และ Inspection Engineer | ✅ กว้างกว่าที่คิดไว้ |
| Decision horizon | ยังไม่ระบุตัวเลขเจาะจงใน docx เช่นกัน (มีแค่ FR-FU-014 "Forecast Time to Constraint" แบบ "ชั่วโมงหรือวัน") | ❌ ยังเปิด — เหมือน OI list |
| ความแม่นยำขั้นต่ำ | docx ไม่ผูก SLA ตายตัว แต่ให้กรอบ Model KPI ละเอียด (§8.3): MAE, RMSE, Normalized MAE, Prediction Bias, error แยกตาม crude type/throughput/operating mode/หลัง TAM vs ปลาย run — **ดีกว่ากรอบเดิมที่มีแค่ within±5/10°C** | ❌ ยังไม่ปิดตัวเลข แต่กรอบวัดชัดขึ้นมาก |
| Error ที่ยอมรับไม่ได้ | docx เน้น**False Cleaning Recommendation** เป็น Business KPI ตรง ๆ (§8.1: "การลดจำนวน False Cleaning Recommendation") — **สอดคล้องกับที่ยืนยันไว้ว่า False Positive อันตรายกว่า** | ✅ สอดคล้องกัน |
| อัปเดตข้อมูล | docx ไม่ผูกความถี่ตายตัว มีแค่ OI-018 "Refresh Frequency ของ Dashboard" เป็น open issue รอ System Owner ยืนยัน | ✅ ปิดแล้วจากการสนทนานี้ (Manual trigger) — ควรใช้คำตอบนี้ปิด OI-018 ใน docx ด้วย |
| KPI | docx แบ่งชัดเจน 3 ชั้น: **Business KPI** (Fuel Gas ลดได้, Energy Cost Saving, CIT Recovery, วันเดินเครื่องเพิ่มขึ้น, ลด false recommendation), **Engineering KPI** (ความแม่นยำ Q/CIT/Fuel Gas/Tube-skin, mass/energy balance closure), **Model KPI** (MAE/RMSE + precision/recall ของ cleaning event detection) | ✅ ละเอียดกว่าที่ร่างไว้เดิมมาก |
| ข้อจำกัด | เพดานล้าง 4 ครั้ง/ปี/HX, TAM_ONLY, งบ 150k/300k/400k บาท (ของเดิมที่มีในโค้ด) — docx ไม่ได้ระบุตัวเลขเหล่านี้ตรง ๆ แต่มี BR-001 "ห้ามแนะนำ Online Cleaning สำหรับ TAM_ONLY" รองรับหลักการเดียวกัน | ✅ |

### 1.4 ขอบเขตโครงการ (จาก docx §6 / Requirement Specification §4)

**In Scope (สรุปจาก IS-001 ถึง IS-015):** ข้อมูล DCS ~95 tags (มี.ค. 2021–กลางปี 2026), CPHT-1+CPHT-2 ทั้ง 16 HX, คำนวณ
Crude Properties จาก Assay, Heat Duty, Clean Baseline (หลัง TAM), Performance Degradation, Cleaning Detection, CIT
Analysis, Furnace Impact (Fuel Gas/Tube-skin/COT/Stack/O₂/Draft), Prediction, Web Dashboard, Scenario Analysis

**Out of Scope ระยะแรก (สรุปจาก OS-001 ถึง OS-008):** Closed-loop control, เขียน setpoint กลับ DCS, override alarm/SIS,
Remaining-life analysis แบบสมบูรณ์, ยืนยันชนิดสารเคมีของ fouling deposit, ยืนยัน cleaning event 100%, เปลี่ยน operating
procedure อัตโนมัติ, ติดตั้ง sensor ใหม่ — **[✅ ตรงกับที่ระบบปัจจุบันทำอยู่แล้ว ไม่มีจุดไหนล้ำขอบเขตนี้]**

**เพิ่มเติมจากการยืนยัน 2026-07-16 (docx ไม่ได้ระบุไว้):** **ระบบ Login / User Role / RBAC** — ไม่ทำในเฟสนี้ ระบบเปิดดูได้
ทุกคนเหมือนเดิม (ไม่ auth) รวมถึง Alert/Notification และ REST API แบบเต็มที่ผูกกับ RBAC (ดู §0, §2.1, §2.4, §2.5) ก็เลื่อนไป
เป็น backlog ด้วยเหตุผลเดียวกัน

---

## 2. Requirements & Constraints

> โครงสร้างหัวข้อนี้ยึดตาม docx "Requirement Specification" (เอกสารที่สอง หลังจาก Business Problem) ซึ่งละเอียดกว่ากรอบ
> เดิมมาก — สรุปเป็นหมวดพร้อม ID เพื่อ trace กลับไป docx ได้ ไม่ก็อปทุกแถว

### 2.1 Business Requirements
มาจาก docx §"3. Business Objectives" (BO-001 ถึง BO-010) + §"5. Stakeholder Requirements" (ST-001 ถึง ST-010) +
§"6. User Roles and Permissions" (RL-001 ถึง RL-007)

- **BO-001 ถึง BO-010** ครอบคลุมตั้งแต่ประเมินสมรรถนะ HX รายตัว → ประเมิน Fouling Trend → CIT Deficit → Fuel Penalty →
  ติดตามข้อจำกัดเตา → ตรวจจับ Cleaning Event → จัดลำดับ HX → คาดการณ์แนวโน้ม → Scenario Analysis → ลดเวลาวิเคราะห์ manual
  — แต่ละตัวมี "ผู้รับผิดชอบยืนยัน" ระบุไว้ (เช่น BO-001 = Process Engineer, BO-004 = Energy Engineer, BO-005 = Furnace
  Specialist) **[ต้องนัดคนกลุ่มนี้มายืนยันจริง ไม่ใช่แค่ระบุชื่อ role ไว้เฉย ๆ]**
- **RL-001 ถึง RL-007** กำหนด role 7 แบบ (Viewer, Operator, Process Engineer, Maintenance Planner, System Owner,
  Administrator, Data Engineer) พร้อม permission matrix (ดู/แก้ limit/ยืนยัน cleaning/run scenario/จัดการผู้ใช้) —
  **📋 ตัดออกจาก scope เฟสนี้ตามที่ยืนยันแล้ว (ไม่ทำ login)** เก็บ matrix นี้ไว้เป็นแบบร่างสำหรับตอนที่ระบบขยายไปมีผู้ใช้
  หลายสิทธิ์จริง ๆ — ระหว่างนี้ทุกคนที่เข้าถึงแดชบอร์ดถือว่ามีสิทธิ์เท่ากันหมด (เหมือน Viewer+Process Engineer รวมกัน แต่ไม่มี
  การล็อกอินแยกตัวตน)

### 2.2 Data Requirements
มาจาก docx §"7.1 Data Ingestion" (FR-DI-001 ถึง 008) + §"7.2 Data Quality" (FR-DQ-001 ถึง 012) + §"11. Data Dictionary
Template"

- **Data Ingestion:** ดึงจาก DCS/Historian 95 tags, นำเข้า Crude Assay + Configuration + วันที่ TAM, รองรับ incremental
  load, **ห้ามแก้ไขข้อมูลต้นฉบับ** (immutable/"Bronze layer" — ตรงกับหลักการ backup อัตโนมัติที่มีอยู่แล้ว), เก็บ job log
  **[✅ ส่วนใหญ่มีแล้วใน `01_data_cleaning.ipynb` + backup mechanism ของ `run_all.py`; ❌ ยังไม่มี job log แบบเป็นทางการ, ❌ ยังไม่รองรับ scheduled/incremental load เพราะเป็น manual trigger เต็มไฟล์เสมอ]**
- **Data Quality:** missing value, timestamp ซ้ำ, range, flatline, spike, gap, unit, mass/energy balance, assay
  mapping, configuration, data-quality score รวม **[⚠️ มีบางส่วนกระจายอยู่ (outlier/IQR ใน `01_data_cleaning.ipynb`,
  chain-consistency check) แต่ไม่ได้รวมเป็น "Data Quality Score" เดียวต่อ HX ตาม FR-DQ-012]**
- **Data Dictionary Template:** ต้องมีฟิลด์ Tag ID/Name/Description/Equipment/Process Side/Measurement Type/Unit/
  Sampling Frequency/Valid Min-Max/Warning Min-Max/Critical Min-Max/Aggregation Rule/Missing Rule/Source
  System/Sensor Type (Measured/Calculated/Inferred)/Owner/Criticality **[❌ ยังไม่มีเป็นทางการ — `cpht_config.py` มีแค่ tag
  mapping ไม่มี valid/warning/critical band ต่อ tag — นี่คือช่องว่างสำคัญที่ควรทำก่อน เพราะ Data Quality (FR-DQ) และ
  Alert (AL-*) ทั้งหมดต้องพึ่งค่าพวกนี้]**
- ไม่มี maintenance/cleaning log ย้อนหลังอย่างเป็นทางการ — ยืนยันซ้ำจาก docx เอง (BP-005) ตรงกับที่ระบุไว้ในไฟล์นี้เดิม

### 2.3 Functional Requirements
มาจาก docx §"7.3–7.8" (FR-PM, FR-HX, FR-CB, FR-CL, FR-FU, FR-PR รวม ~60 requirement) + §"8. หน้าจอ" (8.1–8.6) + §"12. API"

สรุปตามกลุ่ม พร้อมสถานะ:

| กลุ่ม FR | เนื้อหา | สถานะ |
|---|---|---|
| Process Mode (FR-PM-001~011) | จำแนก NORMAL/STARTUP/SHUTDOWN/RATE_CHANGE/FEED_CHANGE/HX_SWAP/SUSPECTED_CLEANING/POST_CLEAN/TAM/SENSOR_FAILURE/UNKNOWN | ⚠️ มีบางส่วน (`Operating_State.csv` มี NORMAL/SUBSTITUTE_ACTIVE/OFF ฯลฯ) แต่ไม่ครบ 11 mode ตาม spec — ไม่มี SUSPECTED_CLEANING/POST_CLEAN เป็น label แยก |
| HX Performance (FR-HX-001~010) | Q cold/hot, energy-balance error, UA, effectiveness, fouling index, Q loss, fouling rate, confidence, E101G inferred | ✅ ส่วนใหญ่มีแล้ว (Q cold-side, fouling rate robust) — Q hot-side/UA/effectiveness ไม่ทำเพราะ hot-side data ไม่น่าเชื่อถือ (ตัดสินใจแล้วใน `02_Requirement_v2_SSOT.md` §3.2) |
| Clean Baseline (FR-CB-001~008) | clean-reference window, ตัด startup, ควบคุม crude rate/assay/hot-stream, แยก equipment era, baseline version | ✅ ตรงกับ initiation-phase baseline ที่มีอยู่ |
| Cleaning Detection (FR-CL-001~009) | Q/temp/UA recovery, configuration change, data gap, แยก process change, **ให้ user confirm/reject event**, audit trail, confidence level | ⚠️ ตรวจจับอัตโนมัติมีแล้ว แต่ **ไม่มี UI ให้ engineer confirm/reject เหตุการณ์ (FR-CL-007/008)** — เป็นช่องว่างสำคัญเพราะกระทบความน่าเชื่อถือของทุก ranking ต่อจากนี้ |
| CIT & Furnace Impact (FR-FU-001~014) | Actual/Expected CIT, CIT Deficit, Furnace Duty/Fuel Gas Penalty, Fuel Gas/COT/Tube-skin/CIT Floor/Stack/O₂/Draft headroom, binding constraint, forecast time-to-constraint | ✅ มีเกือบครบใน `cleaning_scheduler_network.py` + furnace panel — "binding constraint" (FR-FU-013, หา constraint ที่ margin ต่ำสุด) ยังไม่ชัดว่ามี logic แยกเฉพาะหรือเปล่า ควรตรวจสอบ |
| Cleaning Prioritization (FR-PR-001~008) | rank, fuel saving, feasibility, risk, confidence, ห้ามแนะนำ TAM-only online, จำลองผลหลังล้าง, แสดงเหตุผล | ✅ มีแล้วใน notebook 8/16 — BR-001 (ห้ามแนะนำ TAM-only online) มีอยู่จริงผ่าน `bypass_config.py` |
| หน้าจอ (8.1–8.6) | Executive Overview, CPHT Network, HX Detail, Furnace Constraint, Scenario Analysis (**ตัด Login ออกจาก scope แล้ว**) | ⚠️ มี Overview/HX Detail/Furnace/Plan/Forecast/Model/Evidence (7 แท็บ) ครบทุกหน้าที่ยังอยู่ใน scope — เหลือแค่ **Scenario Analysis ยังไม่ใช่หน้า interactive เต็มรูปแบบ** ตาม spec (input HX selection/cleaning order/crude rate/COT target ฯลฯ) เป็นช่องว่างที่ควรทำต่อ |
| API (API-001~014) | REST endpoints ครบ (overview, hx, hx/trend, furnace/status, events, scenario/run, recommendations, data-quality, config/limits, model/status, audit-log) | 📋 **Backlog** — `backend/server.py` มีแค่ upload + trigger pipeline ไม่ใช่ REST API แบบนี้ ส่วนที่ผูกกับ RBAC (config/limits PUT, audit-log) เลื่อนไปพร้อม login แต่ endpoint อื่น (hx/trend, scenario/run) ทำได้อิสระถ้าต้องการ backend แยกจริงจัง |

### 2.4 Non-functional Requirements
มาจาก docx §"13. Non-functional Requirements" (NFR-001 ถึง 017)

| หมวด | ตัวอย่าง requirement | สถานะ |
|---|---|---|
| Performance | Dashboard โหลด ≤5 วินาที | ยังไม่เคยวัด formally |
| Security | Role-based access, DCS connection read-only | 📋 RBAC ตัดออกจาก scope เฟสนี้ (ไม่ทำ login); ✅ read-only อยู่แล้วโดยธรรมชาติ (ไม่มี write-back) |
| Traceability/Auditability | ทุกผลระบุ data/model version, log การแก้ limit/ยืนยัน event | ⚠️ มี evidence.json (บางส่วน) แต่ไม่มี audit log ของการแก้ limit เพราะไม่มีใครแก้ limit ผ่าน UI ได้อยู่แล้วตอนนี้ |
| Maintainability | Tag mapping และ Limit ต้องแยกจาก code | ⚠️ Tag mapping แยกแล้ว (`cpht_config.py`) แต่ furnace limit ยัง hard-code ใน `build_dashboard_topology.py` พร้อม flag `limit_assumed=True` |
| Reliability | Pipeline ล้มเหลวต้องแจ้งเตือน | ❌ ไม่มี notification เลย (manual trigger, ดู error เองใน terminal) |
| Explainability | Recommendation ต้องมีเหตุผล | ✅ มีอยู่แล้ว (`cleaning_plan.json` มี reasoning ต่อ HX) |
| Reproducibility | Input+version เดิม → output เดิม | ✅ ด้วย backup อัตโนมัติก่อนรันทุกครั้ง |
| Scalability | รองรับหลายปีไม่ต้องโหลดทั้งหมดบน browser | ยังไม่เคยทดสอบกับข้อมูลที่ยาวกว่านี้ |
| Model Safety | เตือนเมื่อทำนายนอก operating envelope | ❌ ไม่มี out-of-distribution warning |

### 2.5 Safety and Operational Constraints
มาจาก docx §"9. Business Rules" (BR-001~018) + §"10. Alert Requirements" (AL-001~015) + ตัวเลข limit ที่เคยสำรวจไว้ก่อนหน้า

**ค่า limit ที่ใช้อยู่ในโค้ด (ทั้งหมด flag `limit_assumed=True` — ตรงกับ OI-005 ถึง OI-010 ของ docx ที่ยังเปิดอยู่):**

| ข้อจำกัด | ค่าที่เดินอยู่ | Limit ในโค้ด | ตรงกับ Open Issue |
|---|---|---|---|
| CIT floor | ~258°C | 250°C | OI-005 |
| COT limit | ~340°C | 345°C | OI-006 |
| Tube-skin alarm | ติดตาม 4 pass | 400°C | OI-007 |
| Fuel Gas Flow max | ~6.66 t/h | 9.0 t/h | OI-008 |
| Fuel Gas Pressure min | ~1.82 kg/cm²g | 2.5 kg/cm²g | OI-009 |
| O₂/Draft range | ~2.52% / -3.02 mmH₂O | 1.5-4.5% / -6 ถึง 0.5 | OI-010 |

**Business Rules ที่เกี่ยวกับความปลอดภัย (สถานะเทียบโค้ด):**
- BR-001 ห้ามแนะนำ online cleaning สำหรับ TAM_ONLY — ✅ มีแล้ว
- BR-002 ต้องระบุ E101G เป็น Inferred — ✅ มีแล้ว (ไม่มี sensor, mass-balance infer)
- BR-006 ต้องใช้ tube-skin pass ที่ร้อนสุดเป็น worst case — ⚠️ มี `SKIN_ALARM=400.0` ติดตามทุก pass แต่ต้องยืนยันว่า logic เลือก worst-case จริงหรือเลือกเฉลี่ย
- BR-014 recommendation ต้องไม่ทำให้ COT เกิน limit — ควรตรวจสอบว่า optimizer มี hard constraint นี้จริงหรือเป็นแค่ advisory
- BR-018 ผลรวม benefit หลาย HX ห้ามบวกตรง ๆ ต้องผ่าน network model — ✅ ตรงกับเหตุผลที่มี `cleaning_scheduler_network.py` (v2) แยกจาก v1

**Alert Requirements (AL-001~015):** ครอบคลุม CIT ต่ำกว่า warning/floor, tube-skin ใกล้/เกิน limit, fuel gas flow/pressure
headroom ต่ำ, COT ใกล้ limit, O₂/draft/stack temp ผิดปกติ, sensor missing, model นอก operating range, suspected
cleaning, fouling rate ผิดปกติ, time-to-constraint ต่ำ — **📋 Backlog (Won't Have Now)** เพราะไม่มีกลไก push
notification/ผู้รับที่ระบุตัวตนได้เลย (dashboard เป็นแบบเปิดดูเท่านั้น ไม่มี login) **แต่รายการเงื่อนไข 15 ข้อนี้ยังมีประโยชน์
มาก** — เอาไปทำเป็น "แถบเตือนในหน้า Overview" แบบ passive (ไม่ push ออกไปหาใคร แค่ขึ้นสีแดง/เหลืองในแดชบอร์ดเมื่อเข้าเงื่อนไข)
ได้โดยไม่ต้องรอระบบ login เลย — ควรพิจารณาทำเวอร์ชันนี้ก่อนเป็นงานถัดไป

**⚠️ ข้อขัดแย้งที่ต้องแก้ก่อนใช้งานจริง (คงไว้จากร่างก่อนหน้า):** สูตร `engineering_priority` ปัจจุบัน (notebook 8/16)
ตั้ง safety weight = 2× energy weight โดย default ซึ่งเอนไปทาง "แนะนำล้างง่ายเมื่อสงสัยเรื่อง coking" (เอนด้าน False
Negative) — ขัดกับที่ยืนยันไว้ในหัวข้อ 1 ว่า **False Positive อันตรายกว่า** ต้องทบทวนน้ำหนักนี้ก่อนใช้ ranking ตัดสินใจจริง
docx เองก็สนับสนุนมุมนี้ผ่าน Business KPI "ลดจำนวน False Cleaning Recommendation" (§8.1)

---

## 3. Data Inventory / Understanding
_(ยังไม่ขยาย — docx มี Data Dictionary **Template** เท่านั้น (โครงฟิลด์ ไม่ใช่ตารางข้อมูลจริงต่อ tag) ต้องเอา 95 tags จริง
มากรอกฟิลด์: Valid Min/Max, Warning/Critical Band, Aggregation Rule, Sensor Type ฯลฯ ตาม template นั้น — งานถัดไปที่ควร
ทำเป็นอันดับแรกเพราะ Data Quality (2.2) และ Alert (2.5) ทั้งหมดต้องพึ่งตารางนี้)*

## 4. Data Architecture Design
_(ยังไม่ขยาย — docx ไม่ได้ลง architecture diagram ระบุแค่ "Deployment Type: Internal Web Application" และ "DCS
Integration: Read-only" — ต้องออกแบบเพิ่มเอง: bronze/silver/gold layer ตาม FR-DI-006 (immutable raw), การจัดเก็บ
Data Dictionary/Limit แยกจาก code ตาม NFR-007/008)*

## 5. ขั้นตอน Data Engineering
### Step 1: Data Ingestion → FR-DI-001~008
### Step 2: Timestamp Alignment → ไม่มีใน docx โดยตรง (implicit ใน FR-DI, ควรเพิ่มเป็น requirement แยก)
### Step 3: Data Cleaning → FR-DQ-001~012
### Step 4: Data Transformation → FR-PM (process mode) + FR-HX (Q calculation)
### Step 5: Data Quality Testing → FR-DQ-012 (data quality score) + AC-005/AC-006 (acceptance criteria)
_(แมปแล้วกับ docx — รายละเอียดการ implement ยังต้องเขียนเพิ่มเอง)*

## 6. การเตรียมข้อมูลสำหรับ ML
_(ยังไม่ขยาย — docx ไม่ได้แบ่ง Target/Manipulated/Disturbance/State/Constraints ตรง ๆ แต่ FR-FU (furnace impact) และ
FR-HX (HX performance) ให้ราย list ตัวแปรที่ครบกว่าที่ร่างไว้เดิม ใช้เป็นฐานแบ่งกลุ่มได้)*

## 7. Feature Engineering
_(ยังไม่ขยาย — คงเดิม: อ้างอิง `cpht_features.py`, ย้ำห้าม data leakage ตรงกับ BR-005 "ห้ามใช้ข้อมูล Future ในการ Train หรือ Prediction")*

## 8. Train/Test Split Strategy
_(ยังไม่ขยาย — docx ไม่ได้ระบุ split strategy ตรง ๆ ต้องตัดสินใจเองตามที่ร่างไว้เดิม)*

## 9. Baseline
_(ยังไม่ขยาย — persistence baseline ชนะ ML ทุกตัว — docx §8.3 ให้กรอบ error-breakdown ที่ควรใช้ validate finding นี้เพิ่ม เช่น error แยกตาม crude type/throughput/หลัง TAM vs ปลาย run)*

## 10. เอกสารที่ควรมีเพิ่ม
จาก docx ที่มีอยู่แล้วแต่ยังไม่ implement เป็นโค้ด/ข้อมูลจริง:
- **Data Dictionary** ตัวจริง (docx มีแค่ template — §11)
- **Requirement Traceability Matrix** ตัวจริง (docx §16 มี BO→FR→Screen→AC แล้ว แต่ยังไม่เทียบกับโค้ดจริงทีละบรรทัด)
- **Definition of Done** ต่อ requirement (docx §18)

## 11. Roadmap
_(ยังไม่ขยาย — ควรอิง docx §15 "Requirement Priority Summary" ที่จัดตาม MoSCoW ไว้แล้ว: Data Ingestion/Quality/Tag
Mapping/Configuration Timeline/Q Calculation/Clean Baseline/CIT Deficit/Furnace Constraint Dashboard/E101G Inference
= **Must** (ส่วนใหญ่มีแล้ว), Cleaning Event Detection/Forecasting/Scenario Analysis/Cleaning Optimization/Cost Saving
= **Should** (บางส่วนมีแล้ว), Automatic DCS Control/Full Remaining Life Model = **Won't Have Now** (ตรงกับที่ตัด scope
ไว้แล้ว) — ใช้ลำดับนี้เป็นฐาน roadmap ได้เลย ไม่ต้องคิดใหม่)*

**เพิ่มเข้ากลุ่ม Won't Have Now (ตัดสินใจ 2026-07-16, docx เดิมไม่ได้จัดกลุ่มไว้):**
Login / User Roles & Permissions (RL-*) / Alert push notification (AL-*, ยกเว้นเวอร์ชัน passive ใน-หน้าเว็บที่แนะนำไว้ใน
§2.5) / REST API ส่วนที่ผูกกับ RBAC (config/limits PUT, audit-log) — ทั้งหมดนี้เก็บ requirement ไว้ในไฟล์นี้เป็นแบบร่างที่
"ดีและใช้ได้จริงเมื่อถึงเวลา" ไม่ต้องเขียนใหม่ตอนขยายระบบในอนาคต แค่ไม่ทำตอนนี้

---

## Open Issues (รวมจาก docx OI-001~020 + open items จากการสนทนานี้)

จาก docx §"17. Open Issues และข้อมูลที่ต้องยืนยัน" มี 20 ข้อ (OI-001 ถึง OI-020) ทั้งหมดยังสถานะ **Open** ตัวที่สำคัญ/
เกี่ยวกับที่คุยกันไปแล้วในไฟล์นี้:

| OI | ประเด็น | เกี่ยวข้องกับ | สถานะล่าสุด |
|---|---|---|---|
| OI-005 ถึง OI-010 | CIT Floor, COT Limit, Tube Skin, Fuel Gas Flow/Pressure, O₂/Draft — เป็น Approved Limit จริงหรือ Guideline | §2.5 | ยังเปิด — ต้องนัดวิศวกรเตายืนยัน |
| OI-018 | Refresh Frequency ของ Dashboard | §1.3 | **✅ ปิดแล้ว** — ยืนยันว่า Manual trigger ต่อไป (2026-07-16) |
| OI-019 | ผู้ใดมีสิทธิ์ยืนยัน Cleaning Event | §2.1 (RL-*) | **บางส่วนปิดแล้ว** — เพราะไม่ทำ login เฟสนี้ จึงยืนยันแบบไม่ผูกตัวตนผู้ใช้ (ใครเข้าเว็บก็กด Confirm/Reject ได้ ไม่มี audit-by-user) ยัง**เปิด**เฉพาะประเด็นว่าจะทำปุ่ม confirm/reject นี้เมื่อไหร่ (FR-CL-007/008 ยังไม่มี UI) |
| OI-001, OI-002 | จำนวน HX จริง 16 ตัวหรือมากกว่า, arrangement ตาม P&ID revision ล่าสุด | §1.4, §3 | ยังเปิด — ควรตรวจกับ P&ID ล่าสุดเทียบ `cpht_config.py` |
| OI-004, OI-016, OI-017 | HX ทุกตัวถูกล้างใน TAM หรือไม่, มี operator logbook เก่าไหม, มี modification ปี 2021-2026 ไหม | §2.2, §3 | ยังเปิด — ทั้งหมดคือ "maintenance log ย้อนหลัง" ที่ระบุไว้แล้วว่าไม่มี |

**Open items เพิ่มเติมจากการสนทนานี้ (ไม่อยู่ใน docx):**
1. Decision horizon หลักที่ใช้ฟันธงแผนล้าง (30/60/90 วัน?)
2. เกณฑ์ความแม่นยำขั้นต่ำเชิงตัวเลข ที่ decision horizon นั้น (docx ให้กรอบ metric แต่ไม่ให้ threshold ตายตัวเช่นกัน)
3. ทบทวนน้ำหนัก safety:energy ใน `engineering_priority` ให้ตรงกับ False-Positive-averse ที่ยืนยันไว้ (§2.5)
4. §2.1-2.5 เนื้อหาข้างบนเป็นการสรุป/cross-reference จาก docx — ยังต้องให้เจ้าของโปรเจกต์ตรวจทานความถูกต้องของสถานะ
   "มี/ไม่มี/บางส่วน" ที่ผมประเมินไว้ เพราะบางจุดผมอนุมานจากโค้ดที่อ่านได้ ไม่ได้ทดสอบจริงทุกเส้นทาง (เช่น BR-006, BR-014)
