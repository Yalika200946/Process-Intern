# วิธีรันระบบ CPHT Predictive Maintenance

## 1. เปิด Dashboard (ดูอย่างเดียว)
```bash
cd dashboard
python -m http.server 8811
```
เปิด http://localhost:8811/  (ไฟล์หลักคือ `dashboard/index.html` — เวอร์ชันใหม่ แทน `dashboard_pro.html` เดิม)

## 2. เปิด Dashboard + ฟังก์ชันอัปโหลด/วิเคราะห์ใหม่ (แนะนำ)
```bash
python backend/server.py 8899
```
เปิด http://localhost:8899/  → ใช้แท็บ **โมเดล & Optimization** ได้ครบ:
- **อัปเดตเร็ว** — อัปโหลดไฟล์ process แบบ cleaned (Timestamp + tag ตาม `cpht_config`) → รีเฟรช P&ID + Furnace ทันที
- **วิเคราะห์เต็มรูปแบบ** — อัปโหลด raw Excel (หรือเว้นว่าง = ใช้ข้อมูลปัจจุบัน) → รัน pipeline ทุก notebook ใหม่ (หลายนาที) แล้วกดรีเฟรชหน้าเมื่อเสร็จ

## 3. รัน pipeline เต็มจาก command line
```bash
python pipeline/run_all.py                     # recompute จากข้อมูลปัจจุบัน
python pipeline/run_all.py --input new.xlsx    # ใช้ raw Excel ใหม่ (stage ให้ notebook 01)
python pipeline/run_all.py --only 13           # รันเฉพาะตัว export (debug)
python pipeline/run_all.py --from 06           # รันตั้งแต่ 06 (fouling forecast) เป็นต้นไป
```
- รันโน้ตบุ๊กตามลำดับ dependency ใน **UTF-8 mode** (แก้ปัญหา encoding บน Windows)
- สำรองข้อมูลไป `Data/backup_<เวลา>/` และ `dashboard/data/backup_<เวลา>/` ก่อนเสมอ (`--rollback-on-fail` เพื่อย้อนกลับถ้าล้มเหลว)
- หลังรัน 13 (CIT forecast export) จะ **post-process** ให้อัตโนมัติ: `gen_honest_metrics.py` (model_metrics ที่ซื่อสัตย์), `add_forecast_intervals.py` (ช่วงความเชื่อมั่น), `build_dashboard_topology.py` (P&ID + furnace)

## ไฟล์สำคัญ
| ไฟล์ | หน้าที่ |
|---|---|
| `dashboard/index.html` | Dashboard ใหม่ (P&ID + Furnace + Model + Optimization) |
| `dashboard/data/*.json` | ข้อมูลป้อน dashboard (สร้างโดย pipeline) |
| `backend/server.py` | Backend stdlib (เสิร์ฟ + อัปโหลด/วิเคราะห์ใหม่) |
| `pipeline/run_all.py` | Orchestrator รัน notebook chain + post-process |
| `pipeline/gen_honest_metrics.py` | คำนวณ walk-forward CV + persistence (model_metrics ซื่อสัตย์) |
| `notebooks/build_dashboard_topology.py` | สร้าง `pfd_topology.json` จาก `cpht_config` |
| `notebooks/add_forecast_intervals.py` | เพิ่มช่วงความเชื่อมั่นให้ forecast |
| `pipeline/phm_analysis.py` + `notebooks/phm_config.py` | PHM: RUL (Monte-Carlo), Weibull survival/hazard, propagation model-compare, degradation drivers → `rul/reliability/propagation_models/drivers.json` |
| `pipeline/export_hx_timeseries.py` | ส่งออก per-HX time-series (U_relative/Q/predicted/deviation/temps + run events + fouling rate) → `hx_timeseries.json` สำหรับแท็บ "HX รายตัว" |

## แท็บ "HX รายตัว" + "เตา & Optimization" (ใหม่)
- **HX รายตัว** — เลือก HX → กราฟ U_relative sawtooth (เส้น clean/50/30 + จุดสลับเชลล์/TAM), Q duty, **ค่าทำนาย vs จริง**, temps, ตาราง fouling rate ต่อ run (เหมือน notebook 02 §3.2)
- **เตา & Optimization** — รูปเตา F101 สด (4 passes สีตาม skin temp), Problem cascade มีไฟสถานะสด, **constraint ทั้งหมด 13 ตัว จัด 5 กลุ่ม พร้อมค่าปัจจุบัน+setpoint+limit (แก้ได้)**, ตาราง pass conv/skin/coil, และ **What-if optimization** (ปรับค่าเศรษฐกิจสมมติ → ล้างตามลำดับได้ CIT/FG/฿/CO₂ + payback)

## Prognostics & Risk (PHM) — แท็บ "พยากรณ์ & ความเสี่ยง"
รัน `python pipeline/phm_analysis.py` (หรือรวมอยู่ใน `run_all.py` แล้ว) → แท็บนี้แสดง:
- **RUL** อายุคงเหลือก่อนล้าง P10/P50/P90 (Monte-Carlo) + P(ล้างใน 30/60/90 วัน)
- **Reliability/Hazard** — Weibull survival R(t) + hazard rate + MTBC
- **เทียบโมเดลการเสื่อม** (linear/asymptotic/power/GP) + backtest out-of-sample
- **Degradation drivers** — SHAP ตัวแปรที่มีผล (film temp/flow/asphaltene/API) + lever ลดอัตราเสื่อม
- หมายเหตุ honesty: driver CV R²<0 (n น้อย) → เป็น associative ไม่ใช่ causation; per-HX Weibull n<4 ใช้ pooled shape
ปรับพารามิเตอร์ PHM ได้ที่ `notebooks/phm_config.py` (horizons, MC iters, model toggles, Weibull rule)

## หมายเหตุสำคัญ (ผลวิเคราะห์ ML)
โมเดล CIT ผ่าน **walk-forward CV** แล้ว **แพ้ persistence** (CIT วันนี้=เมื่อวาน) ทุก fold — R²=0.82 ที่เคยโชว์เป็น artifact ของ single-split. ใช้ tree models เพื่อ **SHAP attribution เท่านั้น** และจัดอันดับล้างโดยอิงสัญญาณฟิสิกส์ (Q-duty/fouling rate) เป็นหลัก ดูรายละเอียดในแท็บ *โมเดล & Optimization* และ notebook `6a`.
