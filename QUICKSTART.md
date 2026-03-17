# VitalWatch Dashboard - Quick Start Guide

## What's New

Your VitalWatch system now includes a comprehensive multi-patient monitoring dashboard with the following capabilities:

### New Features Added

#### 1. **Patient Dashboard Interface** (`dashboard/index.html`)
- Multi-patient monitoring interface with department and care-type filtering
- Priority-based layout:
  - Large cards for patients requiring immediate attention (critical/warning)
  - Small thumbnail grid for stable patients
- Real-time WebSocket updates
- Statistics sidebar with patient counts
- Recent alerts panel

#### 2. **Patient Management System** (`src/models/patient.py`)  
- Complete patient data model with attributes:
  - Patient ID, name, department, care type
  - Health status (normal, warning, critical, offline)
  - Mood and movement scores
  - Vital signs and notes
  - Assigned nurse and bed information
- Patient database with filtering capabilities
- Mock data with 8 sample patients across different departments and care types
- Status determination logic based on mood/movement thresholds

#### 3. **Enhanced API Server** (`src/api/server.py`)
**New REST Endpoints:**
- `GET /api/patients` - Retrieve all patients with optional filtering
- `GET /api/patients?department=cardiology&care_type=icu` - Filtered patient list
- `GET /api/patient/{patient_id}` - Get specific patient details
- `POST /api/patient/{patient_id}/status` - Update patient health status
- `GET /api/patient/{patient_id}/stream` - Live video feed for specific patient

**New WebSocket Endpoint:**
- `ws://localhost:8000/ws/patients` - Real-time patient updates
  - Receives initial patient list on connection
  - Real-time status updates when detection occurs
  - Alert notifications

#### 4. **Main Pipeline Integration** (`src/main.py`)
- Initializes patient database on startup
- Integrates ML detection results with patient database
- Updates patient status based on:
  - Mood detection (inverse of severity score)
  - Movement intensity from pose estimation
- Broadcasts patient updates to dashboard via WebSocket
- Maintains backward compatibility with existing pipeline

## How to Use

### Step 1: Start the Application
```bash
# Install dependencies if not already installed
pip install -r requirements.txt

# Run the application
python -m src.main 0  # Use webcam 0, or specify another source
```

The dashboard runs at `http://localhost:8000`

### Step 2: Open the Dashboard
1. Open your browser
2. Navigate to `http://localhost:8000`
3. You should see the VitalWatch header with filter controls

### Step 3: Filter Patients
1. **Select Department**: Choose from Cardiology, Neurology, Trauma, General Medicine, or Respiratory
2. **Select Care Type**: Choose from CCU, ICU, or General Ward
3. The patient list will appear with:
   - Priority section showing critical/warning patients as large cards
   - Stable section showing normal patients as small thumbnails

### Step 4: Monitor Patients
- Watch for status changes in real-time
- Check the sidebar for statistics and recent alerts
- Patient cards color-code by status (green/yellow/red indicators)
- Live video feed appears on each patient card

## Architecture Overview

```
User's Browser
     │
     │ HTTP/WebSocket
     ▼
┌─────────────────────────────────┐
│    FastAPI Web Server           │
│  ├── Static: dashboard/index    │
│  ├── REST API: /api/patients    │
│  └── WebSocket: /ws/patients    │
└─────────────────────────────────┘
     │
     │ Shared Memory
     ▼
┌─────────────────────────────────┐
│   Patient Database              │
│  ├── 8 Mock Patients            │
│  ├── Real-time Status Updates   │
│  └── Department/Care Filtering  │
└─────────────────────────────────┘
     │
     │ Shared Memory (status updates)
     ▼
┌─────────────────────────────────┐
│   ML Detection Pipeline         │
│  ├── Video Input                │
│  ├── YOLOv8 Detection           │
│  ├── Pose/Mood Analysis         │
│  └── Status Calculation         │
└─────────────────────────────────┘
```

## Patient Data Flow

1. **ML Pipeline** detects mood and movement
2. **Results** are converted to mood/movement scores (0-1)
3. **Patient Status** is updated in database
4. **WebSocket** broadcasts update to dashboard
5. **Dashboard** re-renders affected patient cards with new status
6. **Sidebar statistics** update automatically

## Key Files Modified/Created

| File | Changes |
|------|---------|
| `dashboard/index.html` | Complete redesign with multi-patient layout, filters, and WebSocket client |
| `src/models/patient.py` | **NEW** Patient model, database, status logic |
| `src/api/server.py` | Added patient endpoints, new WebSocket, patient DB integration |
| `src/main.py` | Patient DB initialization, status updates, broadcast integration |

## Demo Data Included

8 sample patients across different departments for immediate testing:

- **Cardiology CCU**: John Anderson (ICU-101), Maria Garcia (CCU-05)
- **Respiratory ICU**: Robert Chen (ICU-102)
- **Neurology**: Lisa Thompson (ICU-103) 
- **Trauma**: James Wilson (ICU-104)
- **General Ward**: Patricia Lee, David Martinez, Karen White

Status updates every ~1 second based on mock ML detection data.

## Testing the Dashboard

### Test 1: Filter by Department
1. Open dashboard
2. Select "Cardiology" from department filter
3. You should see: John Anderson, Maria Garcia, David Martinez
4. Select care type "ICU" and see: John Anderson only

### Test 2: Monitor Status Changes
1. As the ML pipeline runs, watch patient cards in the priority section
2. You should see status indicators pulse
3. Sidebar statistics update in real-time
4. Recent alerts appear as they're generated

### Test 3: WebSocket Connection
1. Open browser DevTools (F12) → Network → WS
2. You should see `/ws/patients` connection established
3. As statuses change, you'll see messages flowing through the WebSocket

## Customization Options

### Add More Departments
Edit `src/models/patient.py` - add to `Department` enum and update `dashboard/index.html` filter options

### Modify Status Thresholds  
Edit `update_status()` method in `Patient` class to adjust mood/movement sensitivity

### Change Colors
Edit CSS variables in `dashboard/index.html` `:root` section

### Add More Sample Patients
Add to `_initialize_mock_data()` in `PatientDatabase` class

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Empty patient list | Make sure to select a department AND care type from filters |
| WebSocket connection fails | Check server is running, verify URL is correct |
| Video feeds not loading | Ensure camera is accessible and ML pipeline is running |
| Patients not updating | Verify ML pipeline is running and generating scores |
| Page not loading | Check if port 8000 is available, try different port with `--port` arg |

## API Examples

Get all patients in Cardiology/ICU:
```bash
curl "http://localhost:8000/api/patients?department=cardiology&care_type=icu"
```

Get specific patient:
```bash
curl "http://localhost:8000/api/patient/P001"
```

Update patient status:
```bash
curl -X POST "http://localhost:8000/api/patient/P001/status?mood_score=0.8&movement_score=0.5"
```

## Next Steps

1. **Populate Real Patient Data**: Replace mock data with actual patient database integration
2. **Connect to EHR System**: Integrate vital signs from hospital systems
3. **Add Nurse Assignment Logic**: Track which nurse is assigned to which patient
4. **Implement Alert Customization**: Allow per-patient threshold configuration
5. **Add Mobile Support**: Responsive design for tablets/phones
6. **Historical Analytics**: Chart patient trends over time

## Support

See `DASHBOARD.md` for comprehensive documentation including:
- Detailed feature descriptions
- Full API reference
- Architecture diagrams
- Performance considerations
- Advanced customization options

Enjoy your enhanced VitalWatch monitoring experience!
