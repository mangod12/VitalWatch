# VitalWatch Patient Monitoring Dashboard

## Overview

The VitalWatch dashboard is a real-time multi-patient monitoring interface designed for hospital care units. It provides nurses and healthcare workers with a comprehensive view of all patients in their care, with intelligent priority-based layout that highlights patients requiring immediate attention.

## Key Features

### 1. **Smart Patient Display**
- **Priority Section**: Patients with abnormal mood or movement patterns appear as large, prominent cards
- **Stable Patients Section**: Patients with normal vital signs display as small thumbnail cards (similar to video conference layout)
- **Real-time Status Updates**: Patient status updates in real-time via WebSocket connection

### 2. **Department & Care Type Filtering**
- Filter patients by **Department**: Cardiology, Neurology, Trauma, General Medicine, Respiratory
- Filter by **Care Type**: 
  - **CCU** (Coronary Care Unit) - Cardiac-specific intensive care
  - **ICU** (Intensive Care Unit) - General intensive care
  - **General** - Standard hospital ward

### 3. **Real-time Statistics Sidebar**
- **Critical** patients count (red indicator)
- **Warning** patients count (yellow indicator)
- **Normal** patients count (green indicator)
- **Offline** patients count (gray indicator)

### 4. **Recent Alerts Panel**
- Displays last 10 critical alerts
- Shows timestamp for each alert
- Color-coded by severity level

### 5. **Live Video Feed**
- Each patient card includes a live MJPEG stream from their monitoring device
- Streams automatically fallback gracefully if unavailable

## Dashboard Layout

```
┌──────────────────────────────────────────────────────────────────┐
│                         HEADER                                   │
│  VitalWatch  [Department Filter] [Care Type Filter]              │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────┬──────────────────────┐
│                                         │                      │
│  MAIN FEED                              │  SIDEBAR             │
│                                         │  ├── Statistics      │
│  ! PRIORITY SECTION                     │  │   - Critical: X   │
│  ┌─────────────────────┐                │  │   - Warning: Y    │
│  │ Patient 1           │ ┌──────────┐  │  │   - Normal: Z     │
│  │ Status: CRITICAL    │ │ Live     │  │  │   - Offline: W    │
│  │ [Stream]            │ │ Stream   │  │  ├── Recent Alerts   │
│  └─────────────────────┘ └──────────┘  │  │ • Patient X: ...  │
│                                         │  │ • Patient Y: ...  │
│  STABLE PATIENTS SECTION                │  └──────────────────┘
│  ┌──────┐ ┌──────┐ ┌──────┐            │
│  │P 2:  │ │P 3:  │ │P 4:  │            │
│  │Stream│ │Stream│ │Stream│            │
│  └──────┘ └──────┘ └──────┘            │
│                                         │
└─────────────────────────────────────────┴──────────────────────┘
```

## How to Use

### Selecting Patients to Monitor

1. **Open the Dashboard**
   - Navigate to `http://localhost:8000` in your browser
   - The dashboard will load with an empty state

2. **Filter by Department**
   - Click the "Department" dropdown
   - Select any department: Cardiology, Neurology, Trauma, General Medicine, or Respiratory
   - Patients in that department will appear

3. **Filter by Care Type**
   - Click the "Care Type" dropdown
   - Select CCU, ICU, or General Ward
   - The patient list will update to show only matching patients

4. **Combine Filters**
   - Select both a department AND care type for more specific filtering
   - Example: "Cardiology" + "CCU" shows cardiac patients in coronary care

### Reading Patient Status

**Patient Cards show:**
- **Patient Name** at top
- **Care Type** badge (CCU/ICU/GENERAL)
- **Status Indicator** (pulsing dot):
  - 🔴 **Red** = Critical
  - 🟡 **Yellow** = Warning
  - 🟢 **Green** = Normal
- **Live Video Feed** from monitoring camera
- **Status Badge**:
  - Color-coded (green/yellow/red)
  - Text displaying health state

### Priority Alert System

**Patients appear in PRIORITY section when:**
- Mood score is very low (detected sadness/distress)
- Movement patterns are abnormal:
  - Complete immobility for extended period (>30 seconds)
  - Excessive uncontrolled movement
  - Seizure-like activity

**Critical Patients** are displayed as large cards with:
- Bold red border
- Larger video preview
- Prominent status display

**Normal Patients** appear as small thumbnails with minimal info for space efficiency

## API Endpoints

### REST API

#### Get All Patients
```bash
GET /api/patients
GET /api/patients?department=cardiology&care_type=icu
```

Response:
```json
{
  "patients": [
    {
      "id": "P001",
      "name": "John Anderson",
      "department": "cardiology",
      "care_type": "icu",
      "status": "normal",
      "mood_score": 0.8,
      "movement_score": 0.5,
      "assigned_nurse": "Nurse Sarah",
      "bed_number": "ICU-101",
      "last_update": "2024-02-22T10:30:45.123456"
    }
  ],
  "count": 1
}
```

#### Get Specific Patient
```bash
GET /api/patient/{patient_id}
```

#### Update Patient Status
```bash
POST /api/patient/{patient_id}/status?mood_score=0.8&movement_score=0.5
```

#### Get Patient Stream
```bash
GET /api/patient/{patient_id}/stream
```

### WebSocket API

#### Real-time Patient Updates
```
ws://localhost:8000/ws/patients
```

**Message Types:**

1. **Initial Patient List** (on connection)
```json
{
  "type": "patients_list",
  "patients": [...]
}
```

2. **Patient Status Update** (real-time)
```json
{
  "type": "patient_update",
  "patient": {
    "id": "P001",
    "name": "John Anderson",
    "status": "warning",
    "mood_score": 0.3,
    "movement_score": 0.1
  }
}
```

3. **Alert Notification**
```json
{
  "type": "alert",
  "patient_id": "P001",
  "severity": "critical",
  "message": "Abnormal mood detected",
  "timestamp": "2024-02-22T10:30:45.123456"
}
```

## Patient Status Logic

### Status Determination

Status is determined by mood and movement scores (0-1 scale):

```
CRITICAL if:
- Mood score < 0.3 (very sad/distressed) OR
- Movement score < 0.15 (immobile) OR  
- Movement score > 0.95 (excessive movement)

WARNING if:
- Mood score < 0.5 (sad) OR
- Movement between 0.15-0.3 (low activity) OR
- Movement between 0.85-0.95 (high activity)

NORMAL otherwise
```

### Integration with ML Detection

The system integrates with your existing ML pipeline:
- **Mood Detection**: Uses face emotion analysis to score mood
- **Movement Tracking**: Uses pose estimation to calculate movement intensity

### Real-time Updates

Patient status updates automatically as new data arrives from the ML pipeline, typically every 1-2 seconds.

## Customization

### Adding More Departments

Edit `src/models/patient.py`:
```python
class Department(str, Enum):
    CARDIOLOGY = "cardiology"
    # Add more:
    OPHTHALMOLOGY = "ophthalmology"
    DERMATOLOGY = "dermatology"
```

Then add options to the filter dropdown in `dashboard/index.html`:
```html
<option value="ophthalmology">Ophthalmology</option>
<option value="dermatology">Dermatology</option>
```

### Modifying Status Thresholds

Edit the `update_status()` method in `src/models/patient.py` to adjust sensitivity.

### Customizing Dashboard Colors

Edit CSS variables in `dashboard/index.html`:
```css
:root {
  --normal: #22c55e;      /* Green */
  --warning: #eab308;     /* Yellow */
  --critical: #ef4444;    /* Red */
}
```

## Performance Considerations

- **Dashboard loads smoothly** with 50+ patient cards
- **WebSocket connection** maintains real-time sync
- **Automatic reconnection** if connection is lost
- **Graceful degradation** if video streams unavailable

## Browser Compatibility

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Any modern browser supporting:
  - CSS Grid
  - ES6 JavaScript
  - WebSocket API
  - Fetch API

## Troubleshooting

### Dashboard Shows Empty State
- Make sure you've selected a department and care type from the filters
- Check network connection
- Open browser console (F12) for error messages

### Live Video Not Loading
- Check if the platform can access video stream at `/api/patient/{id}/stream`
- Ensure YOLOv8 model is properly initialized
- Check camera feed is accessible

### WebSocket Connection Failed
- Verify API server is running on correct port
- Check firewall settings
- Ensure dashboard is accessing correct URL (not hardcoded localhost)

### Patients Not Updating
- Verify ML pipeline is running and detecting movement/mood
- Check WebSocket connection in browser console
- Ensure patient database was initialized

## Future Enhancements

- Patient detail modals with full vital signs
- Nurse assignment and task management
- Alert history and analytics
- Multi-camera per patient support
- Custom alert thresholds per patient
- Integration with hospital EHR systems
- Mobile-responsive design improvements
- Voice alerts for critical events

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Dashboard (HTML/JS)                      │
│  - Filter & display patients prioritized by status         │
│  - WebSocket for real-time updates                         │
└────────────┬────────────────────────────────────────────────┘
             │
        ┌────▼─────────────────────────────────────────────────┐
        │            FastAPI Server (server.py)                │
        │  ├── REST API: /api/patients, /api/patient/{id}     │
        │  ├── WebSocket: /ws/patients for updates             │
        │  └── MJPEG: /stream, /api/patient/{id}/stream       │
        └────┬─────────────────────────────────────────────────┘
             │
        ┌────▼──────────────────────────────────────────┐
        │    Patient Database (patient.py)              │
        │  - In-memory patient records                  │
        │  - Status tracking & management               │
        │  - Filtering by department/care type          │
        └────┬───────────────────────────────────────────┘
             │
        ┌────▼──────────────────────────────────────────┐
        │    ML Pipeline (main.py)                      │
        │  - Video capture & processing                 │
        │  - Mood/Movement detection                    │
        │  - Status updates to database                 │
        └────────────────────────────────────────────────┘
```

## Support

For issues or feature requests, please refer to the main VitalWatch README.md or contact your development team.
