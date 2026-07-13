# การนำระบบไปใช้ (Deployment) + ความปลอดภัยของข้อมูล

ระบบมี 2 ส่วน: **Model (Python)** ที่คำนวณ → พ่นผลเป็น `dashboard/data/*.json` และ **Web (HTML)**
ที่อ่าน JSON มาแสดง. เลือก deploy ได้ 3 ระดับ ตามว่าจะใช้ **ข้อมูลจริง** หรือแค่ **โชว์ผลงาน**

| ระดับ | คำสั่ง | ข้อมูล | ทำอะไรได้ | หลุดไหม |
|---|---|---|---|---|
| **1. Local (laptop)** | `python backend/server.py 8899` → `localhost:8899` | จริง | ดู + อัปโหลด + วิเคราะห์ใหม่ | ❌ (อยู่บนเครื่องคุณ) |
| **2. Docker (ภายใน)** | `docker build -t cpht .` → `docker run ...` | จริง (mount) | เหมือนระดับ 1 แต่พกพา = ส่งมอบ IT ไป host ภายในได้ | ❌ ถ้าอยู่ในเน็ตเวิร์กโรงงาน |
| **3. Demo (public)** | อัปโหลด `demo/` ขึ้น GitHub Pages/Vercel | **ปลอม (anonymized)** | ดูอย่างเดียว | ✅ ปลอดภัย (ไม่มีข้อมูลจริง) |

---

## ⚠️ หลักความปลอดภัย (สำคัญสุด)
- `dashboard/data/*.json` มี **instrument tag จริง + อุณหภูมิ/flow จริง** = ข้อมูลลับของโรงกลั่น
- **ห้ามขึ้น public host แบบเปิด (Vercel/GitHub Pages) ด้วยข้อมูลจริง** — URL สาธารณะ = ใครก็เห็น
- `.gitignore` ตั้งไว้แล้วให้**ไม่ commit ข้อมูลจริง** (`dashboard/data/*.json`, `Data/`, `uploads/`) → กัน push หลุดขึ้น repo
- ถ้าจะเผยแพร่โค้ดต่อสาธารณะ: `notebooks/cpht_config.py` มี tag จริง → เก็บ repo เป็น **private** หรือเผยแพร่แค่ `demo/`

---

## ระดับ 1 — Local (ตอนนี้)
```bash
python -m http.server 8811 --directory dashboard   # ดูอย่างเดียว → localhost:8811
python backend/server.py 8899                       # ครบ (อัปโหลด/วิเคราะห์) → localhost:8899
python pipeline/run_all.py                          # รัน model ใหม่จากข้อมูลปัจจุบัน
```

## ระดับ 2 — Docker (ส่งมอบให้โรงงาน host ภายใน)
```bash
docker build -t cpht .
docker run -p 8899:8899 -v "C:/Desktop/Bangchak Internship 2026/Data:/data" cpht
# เปิด http://localhost:8899/
```
- ข้อมูลจริงอยู่ที่ **volume ที่ mount (`/data`)** ไม่ฝังใน image
- `CPHT_DATA_DIR=/data`, `CPHT_BIND=0.0.0.0` ตั้งให้ใน Dockerfile แล้ว
- image นี้มีผลวิเคราะห์ปัจจุบันติดมาด้วย → **อย่า push ขึ้น public registry** (ใช้ภายในเท่านั้น)
- อยากได้ full 13-notebook re-run ใน container: build ด้วย `requirements-full.txt` (เพิ่ม tensorflow, image ใหญ่ขึ้นมาก)

## ระดับ 3 — Demo public (โชว์ผลงาน ไม่หลุดข้อมูล)
```bash
python deploy/anonymize_data.py     # สร้างโฟลเดอร์ demo/ (tag+ค่าถูกสุ่มแทน)
```
เอา **เฉพาะโฟลเดอร์ `demo/`** ขึ้น:
- **GitHub Pages:** push `demo/` ไป repo → Settings → Pages → ชี้ที่โฟลเดอร์ → ได้ URL
- **Vercel:** `vercel deploy demo/` (static, ไม่มี build step)
- Demo แสดง banner "DEMO · ข้อมูลจำลอง" + ปิดปุ่มอัปโหลด/วิเคราะห์ (ไม่มี backend)

---

## หมายเหตุสถาปัตยกรรม
- ส่วน **ดู dashboard** = static HTML → host ที่ไหนก็ได้ (นี่คือเหตุผลที่ demo ขึ้น Vercel ได้)
- ส่วน **model/pipeline** = Python (pandas/sklearn/nbconvert) → **Vercel serverless รันไม่ไหว** ต้องมีเครื่องรัน Python (local/Docker/server)
- backend เป็น **Python stdlib ล้วน** ไม่ต้องลง FastAPI/Flask — รันได้บนเครื่องที่มี Python เฉย ๆ
