from flask import Flask, jsonify, request, send_from_directory
import os
import json
import datetime

app = Flask(__name__, static_folder='static', static_url_path='/static')

DEMO_USER_NAME = os.environ.get('DEMO_USER_NAME', 'Demo User')

OPEN_STATES = ['new', 'active', 'awaiting problem', 'awaiting user info', 'awaiting evidence']


def past_datetime(days_ago=0, hours_ago=0, minutes_ago=0):
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=days_ago, hours=hours_ago, minutes=minutes_ago
    )


incidents_db = {
    "INC001001": {
        "number": "INC001001",
        "state": "Closed",
        "short_description": "Email server unresponsive",
        "assignment_group": "Network Support",
        "priority": "1 - Critical",
        "impact": "1 - High",
        "channel": "Phone",
        "category": "Hardware",
        "subcategory": "Server",
        "cmdb_ci": "email-server-01",
        "caller_id": "abel.tuter@example.com",
        "opened_at": past_datetime(days_ago=7, hours_ago=3).isoformat(),
        "sys_created_on": past_datetime(days_ago=7, hours_ago=3).isoformat(),
        "created_by": "abel.tuter",
        "opened_by": "abel.tuter",
        "description": "Users reported being unable to send or receive emails starting around 9:00 AM.",
        "resolution_code": "Solved (Workaround)",
        "resolution_notes": "Primary email server NIC failed. Traffic rerouted to secondary NIC.",
        "closed_at": past_datetime(days_ago=7, hours_ago=1).isoformat(),
        "updated_on": past_datetime(days_ago=7, hours_ago=1).isoformat(),
        "updated_by": "system.auto_close",
        "resolved_by": "network.admin",
        "escalation": "-- None --",
    },
    "INC001002": {
        "number": "INC001002",
        "state": "Resolved",
        "short_description": "Cannot access shared drive 'X:'",
        "assignment_group": "Desktop Support",
        "priority": "2 - High",
        "impact": "2 - Medium",
        "channel": "Email",
        "category": "Software",
        "subcategory": "File Share",
        "cmdb_ci": "shared-drive-corp-fs03",
        "caller_id": "beth.anglin@example.com",
        "opened_at": past_datetime(days_ago=5, hours_ago=2).isoformat(),
        "sys_created_on": past_datetime(days_ago=5, hours_ago=2).isoformat(),
        "created_by": "beth.anglin",
        "opened_by": "beth.anglin",
        "description": "User could not access the corporate shared drive mapped as 'X:'. Error: 'Network path not found'.",
        "resolution_code": "Solved (Permanently)",
        "resolution_notes": "Authentication token for Finance security group expired. Renewed and restarted SMB services.",
        "closed_at": past_datetime(days_ago=5, minutes_ago=30).isoformat(),
        "updated_on": past_datetime(days_ago=5, minutes_ago=30).isoformat(),
        "updated_by": "sarah.jones",
        "resolved_by": "sarah.jones",
        "escalation": "-- None --",
    },
    "INC001003": {
        "number": "INC001003",
        "state": "Closed",
        "short_description": "VPN connection drops frequently",
        "assignment_group": "IT Security",
        "priority": "3 - Moderate",
        "impact": "3 - Low",
        "channel": "Self-service",
        "category": "Network",
        "subcategory": "VPN",
        "cmdb_ci": "vpn-concentrator-02",
        "caller_id": "david.lee@example.com",
        "opened_at": past_datetime(days_ago=3, hours_ago=6).isoformat(),
        "sys_created_on": past_datetime(days_ago=3, hours_ago=6).isoformat(),
        "created_by": "david.lee",
        "opened_by": "david.lee",
        "description": "VPN connection dropping every 15-20 minutes, requiring re-authentication.",
        "resolution_code": "Solved (User Training)",
        "resolution_notes": "High packet loss on user's home internet plus a bandwidth-intensive P2P app in background.",
        "closed_at": past_datetime(days_ago=3, hours_ago=1).isoformat(),
        "updated_on": past_datetime(days_ago=3, hours_ago=1).isoformat(),
        "updated_by": "mark.chen",
        "resolved_by": "mark.chen",
        "escalation": "-- None --",
    },
    "INC001004": {
        "number": "INC001004",
        "state": "Closed",
        "short_description": "Application XYZ not loading for a single user",
        "assignment_group": "Application Support",
        "priority": "4 - Low",
        "impact": "3 - Low",
        "channel": "Email",
        "category": "Software",
        "subcategory": "Application",
        "cmdb_ci": "app-server-xyz-prod",
        "caller_id": "emily.chen@example.com",
        "opened_at": past_datetime(days_ago=2, hours_ago=4).isoformat(),
        "sys_created_on": past_datetime(days_ago=2, hours_ago=4).isoformat(),
        "created_by": "emily.chen",
        "opened_by": "emily.chen",
        "description": "Application XYZ failing to load, showing generic error page 'Error 500'.",
        "resolution_code": "Solved (No Fault Found)",
        "resolution_notes": "Issue isolated to user's browser cache and cookies. Cleared cache resolved the issue.",
        "closed_at": past_datetime(days_ago=2, hours_ago=2).isoformat(),
        "updated_on": past_datetime(days_ago=2, hours_ago=2).isoformat(),
        "updated_by": "ops.admin",
        "resolved_by": "ops.admin",
        "escalation": "-- None --",
    },
    "INC001005": {
        "number": "INC001005",
        "state": "Closed",
        "short_description": "Printer 'PRN-FIN-01' jamming frequently",
        "assignment_group": "Hardware Support",
        "priority": "3 - Moderate",
        "impact": "2 - Medium",
        "channel": "Phone",
        "category": "Hardware",
        "subcategory": "Printer",
        "cmdb_ci": "PRN-FIN-01",
        "caller_id": "george.bailey@example.com",
        "opened_at": past_datetime(days_ago=4, hours_ago=5).isoformat(),
        "sys_created_on": past_datetime(days_ago=4, hours_ago=5).isoformat(),
        "created_by": "george.bailey",
        "opened_by": "george.bailey",
        "description": "Finance printer experiencing frequent paper jams, every 20-30 pages.",
        "resolution_code": "Solved (Hardware Replacement)",
        "resolution_notes": "Replaced worn-out feed roller assembly and realigned paper tray.",
        "closed_at": past_datetime(days_ago=4, hours_ago=1).isoformat(),
        "updated_on": past_datetime(days_ago=4, hours_ago=1).isoformat(),
        "updated_by": "tech.support",
        "resolved_by": "tech.support",
        "escalation": "-- None --",
    },

    # --- Open incidents: opened today ---
    "INC0023228": {
        "number": "INC0023228",
        "state": "New",
        "short_description": "User created a new incident using Ansible Automation Platform",
        "assignment_group": "aap-roadshow",
        "priority": "5 - Planning",
        "impact": "3 - Low",
        "channel": "Email",
        "category": "Inquiry / Help",
        "subcategory": "",
        "cmdb_ci": "",
        "caller_id": DEMO_USER_NAME,
        "opened_at": past_datetime(hours_ago=1).isoformat(),
        "sys_created_on": past_datetime(hours_ago=1).isoformat(),
        "created_by": "aap-roadshow",
        "opened_by": DEMO_USER_NAME,
        "description": "User aap-roadshow successfully created a new incident!",
        "escalation": "-- None --",
        "updated_on": past_datetime(hours_ago=1).isoformat(),
        "updated_by": DEMO_USER_NAME,
    },
    "INC0023229": {
        "number": "INC0023229",
        "state": "New",
        "short_description": "Login page not loading after morning update",
        "assignment_group": "Application Support",
        "priority": "2 - High",
        "impact": "2 - Medium",
        "channel": "Self-service",
        "category": "Software",
        "subcategory": "Application",
        "cmdb_ci": "web-portal-prod",
        "caller_id": "sarah.jones@example.com",
        "opened_at": past_datetime(hours_ago=2).isoformat(),
        "sys_created_on": past_datetime(hours_ago=2).isoformat(),
        "created_by": "sarah.jones",
        "opened_by": "sarah.jones",
        "description": "After this morning's scheduled update, the login page returns a 503 error for approximately 30% of users.",
        "escalation": "-- None --",
        "updated_on": past_datetime(hours_ago=2).isoformat(),
        "updated_by": "sarah.jones",
    },

    # --- Open incidents: recent days ---
    "INC0023230": {
        "number": "INC0023230",
        "state": "New",
        "short_description": "Password reset for LDAP account",
        "assignment_group": "Service Desk",
        "priority": "4 - Low",
        "impact": "3 - Low",
        "channel": "Phone",
        "category": "Software",
        "subcategory": "Account",
        "cmdb_ci": "ldap-server-01",
        "caller_id": "mike.wilson@example.com",
        "opened_at": past_datetime(days_ago=1, hours_ago=3).isoformat(),
        "sys_created_on": past_datetime(days_ago=1, hours_ago=3).isoformat(),
        "created_by": "mike.wilson",
        "opened_by": "mike.wilson",
        "description": "User locked out of LDAP account after multiple failed login attempts.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=1, hours_ago=2).isoformat(),
        "updated_by": "service.desk",
    },
    "INC0023231": {
        "number": "INC0023231",
        "state": "Active",
        "short_description": "Production server high CPU usage",
        "assignment_group": "Network Support",
        "priority": "1 - Critical",
        "impact": "1 - High",
        "channel": "Monitoring",
        "category": "Hardware",
        "subcategory": "Server",
        "cmdb_ci": "prod-app-server-05",
        "caller_id": "monitoring.system",
        "opened_at": past_datetime(days_ago=1, hours_ago=6).isoformat(),
        "sys_created_on": past_datetime(days_ago=1, hours_ago=6).isoformat(),
        "created_by": "monitoring.system",
        "opened_by": "monitoring.system",
        "description": "Automated alert: CPU usage on prod-app-server-05 exceeded 95% for more than 15 minutes.",
        "escalation": "1 - Yes",
        "updated_on": past_datetime(hours_ago=4).isoformat(),
        "updated_by": "network.admin",
    },
    "INC0023232": {
        "number": "INC0023232",
        "state": "New",
        "short_description": "Broken link on company portal homepage",
        "assignment_group": "Application Support",
        "priority": "4 - Low",
        "impact": "3 - Low",
        "channel": "Email",
        "category": "Software",
        "subcategory": "Web",
        "cmdb_ci": "corp-intranet",
        "caller_id": "lisa.park@example.com",
        "opened_at": past_datetime(days_ago=3, hours_ago=2).isoformat(),
        "sys_created_on": past_datetime(days_ago=3, hours_ago=2).isoformat(),
        "created_by": "lisa.park",
        "opened_by": "lisa.park",
        "description": "The 'Benefits Enrollment' link on the main intranet page returns 404.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=3, hours_ago=1).isoformat(),
        "updated_by": "lisa.park",
    },
    "INC0023233": {
        "number": "INC0023233",
        "state": "Active",
        "short_description": "Network outage in Building C, 3rd floor",
        "assignment_group": "Network Support",
        "priority": "1 - Critical",
        "impact": "1 - High",
        "channel": "Phone",
        "category": "Network",
        "subcategory": "LAN",
        "cmdb_ci": "switch-bldgC-3f",
        "caller_id": "facilities@example.com",
        "opened_at": past_datetime(days_ago=2, hours_ago=1).isoformat(),
        "sys_created_on": past_datetime(days_ago=2, hours_ago=1).isoformat(),
        "created_by": "facilities",
        "opened_by": "facilities",
        "description": "All wired and wireless connections on Building C 3rd floor are down. Approximately 40 users affected.",
        "escalation": "1 - Yes",
        "updated_on": past_datetime(days_ago=1).isoformat(),
        "updated_by": "network.admin",
    },
    "INC0023234": {
        "number": "INC0023234",
        "state": "Active",
        "short_description": "Software update failing on finance workstations",
        "assignment_group": "Desktop Support",
        "priority": "3 - Moderate",
        "impact": "2 - Medium",
        "channel": "Email",
        "category": "Software",
        "subcategory": "OS",
        "cmdb_ci": "wsus-server",
        "caller_id": "tom.harris@example.com",
        "opened_at": past_datetime(days_ago=3, hours_ago=5).isoformat(),
        "sys_created_on": past_datetime(days_ago=3, hours_ago=5).isoformat(),
        "created_by": "tom.harris",
        "opened_by": "tom.harris",
        "description": "Windows security update KB5034441 failing with error 0x80070643 on 12 finance department workstations.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=2).isoformat(),
        "updated_by": "desktop.support",
    },
    "INC0023235": {
        "number": "INC0023235",
        "state": "Active",
        "short_description": "Server disk space critically low on DB-PROD-02",
        "assignment_group": "Database Admin",
        "priority": "2 - High",
        "impact": "2 - Medium",
        "channel": "Monitoring",
        "category": "Hardware",
        "subcategory": "Storage",
        "cmdb_ci": "DB-PROD-02",
        "caller_id": "monitoring.system",
        "opened_at": past_datetime(days_ago=4, hours_ago=2).isoformat(),
        "sys_created_on": past_datetime(days_ago=4, hours_ago=2).isoformat(),
        "created_by": "monitoring.system",
        "opened_by": "monitoring.system",
        "description": "Disk usage on DB-PROD-02 at 94%. Transaction logs growing rapidly. Estimated to reach capacity in 48 hours.",
        "escalation": "1 - Yes",
        "updated_on": past_datetime(days_ago=1).isoformat(),
        "updated_by": "dba.team",
    },
    "INC0023236": {
        "number": "INC0023236",
        "state": "Awaiting Problem",
        "short_description": "Intermittent WiFi disconnects in east wing",
        "assignment_group": "Network Support",
        "priority": "3 - Moderate",
        "impact": "2 - Medium",
        "channel": "Self-service",
        "category": "Network",
        "subcategory": "Wireless",
        "cmdb_ci": "wifi-ap-east-07",
        "caller_id": "jennifer.wu@example.com",
        "opened_at": past_datetime(days_ago=5, hours_ago=4).isoformat(),
        "sys_created_on": past_datetime(days_ago=5, hours_ago=4).isoformat(),
        "created_by": "jennifer.wu",
        "opened_by": "jennifer.wu",
        "description": "Multiple users in the east wing reporting WiFi dropping 3-5 times per day for 2-3 minutes each time.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=3).isoformat(),
        "updated_by": "network.admin",
    },
    "INC0023237": {
        "number": "INC0023237",
        "state": "Awaiting User Info",
        "short_description": "Application crash during monthly report generation",
        "assignment_group": "Application Support",
        "priority": "3 - Moderate",
        "impact": "2 - Medium",
        "channel": "Email",
        "category": "Software",
        "subcategory": "Application",
        "cmdb_ci": "reporting-app-prod",
        "caller_id": "kevin.brown@example.com",
        "opened_at": past_datetime(days_ago=6, hours_ago=3).isoformat(),
        "sys_created_on": past_datetime(days_ago=6, hours_ago=3).isoformat(),
        "created_by": "kevin.brown",
        "opened_by": "kevin.brown",
        "description": "The monthly financial report crashes at 75% completion with OutOfMemoryError. Requested user provide the exact report parameters used.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=4).isoformat(),
        "updated_by": "app.support",
    },

    # --- Not updated for 7+ days ---
    "INC0023238": {
        "number": "INC0023238",
        "state": "New",
        "short_description": "Projector flickering in Conference Room A",
        "assignment_group": "Hardware Support",
        "priority": "4 - Low",
        "impact": "3 - Low",
        "channel": "Self-service",
        "category": "Hardware",
        "subcategory": "Display",
        "cmdb_ci": "proj-confA",
        "caller_id": "nancy.drew@example.com",
        "opened_at": past_datetime(days_ago=10, hours_ago=2).isoformat(),
        "sys_created_on": past_datetime(days_ago=10, hours_ago=2).isoformat(),
        "created_by": "nancy.drew",
        "opened_by": "nancy.drew",
        "description": "The projector in Conference Room A flickers intermittently during presentations.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=8).isoformat(),
        "updated_by": "hardware.support",
    },
    "INC0023239": {
        "number": "INC0023239",
        "state": "Active",
        "short_description": "Badge reader not working at entrance B",
        "assignment_group": "Hardware Support",
        "priority": "3 - Moderate",
        "impact": "2 - Medium",
        "channel": "Phone",
        "category": "Hardware",
        "subcategory": "Access Control",
        "cmdb_ci": "badge-reader-entrB",
        "caller_id": "security.desk@example.com",
        "opened_at": past_datetime(days_ago=14, hours_ago=1).isoformat(),
        "sys_created_on": past_datetime(days_ago=14, hours_ago=1).isoformat(),
        "created_by": "security.desk",
        "opened_by": "security.desk",
        "description": "Badge reader at entrance B intermittently fails to read employee badges. Manual override required.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=10).isoformat(),
        "updated_by": "hardware.support",
    },
    "INC0023240": {
        "number": "INC0023240",
        "state": "New",
        "short_description": "Outlook calendar sync issues with mobile devices",
        "assignment_group": "Desktop Support",
        "priority": "4 - Low",
        "impact": "3 - Low",
        "channel": "Email",
        "category": "Software",
        "subcategory": "Email",
        "cmdb_ci": "exchange-server-01",
        "caller_id": "rachel.kim@example.com",
        "opened_at": past_datetime(days_ago=12, hours_ago=3).isoformat(),
        "sys_created_on": past_datetime(days_ago=12, hours_ago=3).isoformat(),
        "created_by": "rachel.kim",
        "opened_by": "rachel.kim",
        "description": "Calendar events created on desktop not syncing to mobile Outlook app. Affects approximately 8 users.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=9).isoformat(),
        "updated_by": "desktop.support",
    },

    # --- Open and older than 30 days ---
    "INC0023241": {
        "number": "INC0023241",
        "state": "New",
        "short_description": "Legacy CRM system migration planning",
        "assignment_group": "Application Support",
        "priority": "5 - Planning",
        "impact": "3 - Low",
        "channel": "Email",
        "category": "Software",
        "subcategory": "Application",
        "cmdb_ci": "crm-legacy-prod",
        "caller_id": "project.office@example.com",
        "opened_at": past_datetime(days_ago=45).isoformat(),
        "sys_created_on": past_datetime(days_ago=45).isoformat(),
        "created_by": "project.office",
        "opened_by": "project.office",
        "description": "Planning ticket for migrating legacy CRM system to new cloud-based platform. Target completion Q4.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=35).isoformat(),
        "updated_by": "project.office",
    },
    "INC0023242": {
        "number": "INC0023242",
        "state": "Active",
        "short_description": "Reconfigure network for new floor plan - Bldg A",
        "assignment_group": "Network Support",
        "priority": "3 - Moderate",
        "impact": "2 - Medium",
        "channel": "Email",
        "category": "Network",
        "subcategory": "LAN",
        "cmdb_ci": "switch-bldgA-2f",
        "caller_id": "facilities@example.com",
        "opened_at": past_datetime(days_ago=35, hours_ago=4).isoformat(),
        "sys_created_on": past_datetime(days_ago=35, hours_ago=4).isoformat(),
        "created_by": "facilities",
        "opened_by": "facilities",
        "description": "Network ports and switch configs need updating to match the renovated floor plan in Building A, 2nd floor.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=20).isoformat(),
        "updated_by": "network.admin",
    },
    "INC0023243": {
        "number": "INC0023243",
        "state": "Active",
        "short_description": "Annual security audit findings remediation",
        "assignment_group": "IT Security",
        "priority": "2 - High",
        "impact": "1 - High",
        "channel": "Email",
        "category": "Network",
        "subcategory": "Security",
        "cmdb_ci": "firewall-main",
        "caller_id": "ciso.office@example.com",
        "opened_at": past_datetime(days_ago=40, hours_ago=2).isoformat(),
        "sys_created_on": past_datetime(days_ago=40, hours_ago=2).isoformat(),
        "created_by": "ciso.office",
        "opened_by": "ciso.office",
        "description": "Remediation of 14 findings from annual penetration test. 8 critical, 6 high severity.",
        "escalation": "1 - Yes",
        "updated_on": past_datetime(days_ago=15).isoformat(),
        "updated_by": "security.admin",
    },
    "INC0023244": {
        "number": "INC0023244",
        "state": "New",
        "short_description": "Upgrade ERP module to version 7.5",
        "assignment_group": "Application Support",
        "priority": "3 - Moderate",
        "impact": "2 - Medium",
        "channel": "Email",
        "category": "Software",
        "subcategory": "Application",
        "cmdb_ci": "erp-prod-cluster",
        "caller_id": "project.office@example.com",
        "opened_at": past_datetime(days_ago=60).isoformat(),
        "sys_created_on": past_datetime(days_ago=60).isoformat(),
        "created_by": "project.office",
        "opened_by": "project.office",
        "description": "Scheduled upgrade of ERP financial module from 7.3 to 7.5 to address performance issues and new regulatory requirements.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=40).isoformat(),
        "updated_by": "app.support",
    },

    # --- Unassigned ---
    "INC0023245": {
        "number": "INC0023245",
        "state": "New",
        "short_description": "Monitor flickering on desk 4B-22",
        "assignment_group": "",
        "priority": "4 - Low",
        "impact": "3 - Low",
        "channel": "Self-service",
        "category": "Hardware",
        "subcategory": "Display",
        "cmdb_ci": "",
        "caller_id": "peter.novak@example.com",
        "opened_at": past_datetime(days_ago=3, hours_ago=5).isoformat(),
        "sys_created_on": past_datetime(days_ago=3, hours_ago=5).isoformat(),
        "created_by": "peter.novak",
        "opened_by": "peter.novak",
        "description": "External monitor on desk 4B-22 flickers when connected via HDMI. Works fine with DisplayPort.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=3, hours_ago=5).isoformat(),
        "updated_by": "peter.novak",
    },
    "INC0023246": {
        "number": "INC0023246",
        "state": "New",
        "short_description": "Request for additional monitor for dual-screen setup",
        "assignment_group": "",
        "priority": "4 - Low",
        "impact": "3 - Low",
        "channel": "Self-service",
        "category": "Hardware",
        "subcategory": "Display",
        "cmdb_ci": "",
        "caller_id": "anna.martinez@example.com",
        "opened_at": past_datetime(days_ago=5, hours_ago=1).isoformat(),
        "sys_created_on": past_datetime(days_ago=5, hours_ago=1).isoformat(),
        "created_by": "anna.martinez",
        "opened_by": "anna.martinez",
        "description": "Requesting a second monitor for productivity. Manager approved.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=5, hours_ago=1).isoformat(),
        "updated_by": "anna.martinez",
    },

    # --- Additional open incidents for variety ---
    "INC0023247": {
        "number": "INC0023247",
        "state": "Awaiting Evidence",
        "short_description": "Suspected phishing email reported",
        "assignment_group": "IT Security",
        "priority": "2 - High",
        "impact": "2 - Medium",
        "channel": "Email",
        "category": "Network",
        "subcategory": "Security",
        "cmdb_ci": "email-gateway",
        "caller_id": "compliance@example.com",
        "opened_at": past_datetime(days_ago=2, hours_ago=5).isoformat(),
        "sys_created_on": past_datetime(days_ago=2, hours_ago=5).isoformat(),
        "created_by": "compliance",
        "opened_by": "compliance",
        "description": "Multiple employees received suspicious email with links to credential-harvesting page. Awaiting email headers and sample for analysis.",
        "escalation": "1 - Yes",
        "updated_on": past_datetime(days_ago=1).isoformat(),
        "updated_by": "security.admin",
    },
    "INC0023248": {
        "number": "INC0023248",
        "state": "Active",
        "short_description": "Backup job failing for file server FS-05",
        "assignment_group": "Network Support",
        "priority": "2 - High",
        "impact": "2 - Medium",
        "channel": "Monitoring",
        "category": "Software",
        "subcategory": "Backup",
        "cmdb_ci": "backup-server-01",
        "caller_id": "monitoring.system",
        "opened_at": past_datetime(days_ago=2).isoformat(),
        "sys_created_on": past_datetime(days_ago=2).isoformat(),
        "created_by": "monitoring.system",
        "opened_by": "monitoring.system",
        "description": "Nightly backup job for FS-05 has failed for 3 consecutive nights. Error: insufficient tape capacity.",
        "escalation": "-- None --",
        "updated_on": past_datetime(days_ago=1).isoformat(),
        "updated_by": "backup.admin",
    },
}

requests_db = {
    "REQ002001": {
        "number": "REQ002001",
        "state": "Closed",
        "stage": "Completed",
        "short_description": "Request for new software license",
        "assignment_group": "Software Asset Management",
        "priority": "3 - Moderate",
        "opened_at": past_datetime(days_ago=9, hours_ago=2).isoformat(),
        "requested_by": "abel.tuter@example.com",
        "requested_for": "abel.tuter@example.com",
        "item_details": {"name": "Adobe Photoshop License", "quantity": 1, "cost_center": "CC-MARKETING"},
        "description": "Need a new license for Adobe Photoshop for upcoming design project.",
        "approval": "Approved",
        "due_date": past_datetime(days_ago=7).isoformat(),
        "closed_at": past_datetime(days_ago=7).isoformat(),
        "updated_on": past_datetime(days_ago=7).isoformat(),
        "updated_by": "sam.specialist",
    },
    "REQ002002": {
        "number": "REQ002002",
        "state": "Closed",
        "stage": "Completed",
        "short_description": "New Laptop Request",
        "assignment_group": "Hardware Procurement",
        "priority": "2 - High",
        "opened_at": past_datetime(days_ago=15).isoformat(),
        "requested_by": "beth.anglin@example.com",
        "requested_for": "charlie.davis@example.com",
        "item_details": {"name": "Standard Developer Laptop Model X", "quantity": 1, "specifications": "16GB RAM, 512GB SSD, Core i7"},
        "description": "New laptop for new hire Charlie Davis, starting next Monday.",
        "approval": "Approved",
        "due_date": past_datetime(days_ago=8).isoformat(),
        "closed_at": past_datetime(days_ago=8).isoformat(),
        "updated_on": past_datetime(days_ago=8).isoformat(),
        "updated_by": "procurement.specialist",
    },
}


def get_next_number(prefix, db_keys):
    if not db_keys:
        return f"{prefix}{'1'.zfill(7)}"
    max_num = 0
    for key in db_keys:
        num_str = key.replace(prefix, "")
        if num_str.isdigit():
            max_num = max(max_num, int(num_str))
    return f"{prefix}{str(max_num + 1).zfill(7)}"


# Incident journal / work notes (keyed by incident number)
comments_db = {}
_comment_seq = 0

# --- Persistence -----------------------------------------------------------
# Incidents live in memory, which is fine until the pod restarts. The
# Automation Orchestrator keeps executions open for far longer than this
# process lives: after a restart the seeded numbers are re-issued and every
# comment or finalize against an older incident fails with "Incident not
# found", which is what breaks the ticket lifecycle mid-demo.
#
# Best effort by design: if STATE_FILE is unset or unwritable the mock still
# runs exactly as before, just without surviving a restart.
STATE_FILE = os.environ.get("SNOW_STATE_FILE", "")


def _persist():
    if not STATE_FILE:
        return
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"incidents": incidents_db,
                       "comments": comments_db,
                       "comment_seq": _comment_seq}, f)
        os.replace(tmp, STATE_FILE)  # atomic, so a crash cannot truncate it
    except OSError as exc:
        app.logger.warning("could not persist state to %s: %s", STATE_FILE, exc)


def _restore():
    global _comment_seq
    if not STATE_FILE or not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE) as f:
            saved = json.load(f)
    except (OSError, ValueError) as exc:
        app.logger.warning("ignoring unreadable state file %s: %s", STATE_FILE, exc)
        return
    # Saved state fully replaces seed data when a state file exists (seeds are
    # only for a never-persisted fresh start). Empty {"incidents": {}} clears all.
    global incidents_db, comments_db
    incidents_db = dict(saved.get("incidents") or {})
    comments_db = dict(saved.get("comments") or {})
    _comment_seq = int(saved.get("comment_seq") or 0)
    app.logger.info("restored %d incidents from %s", len(incidents_db), STATE_FILE)


def _next_comment_id():
    global _comment_seq
    _comment_seq += 1
    return f"COMM{_comment_seq:07d}"


def _append_comment(incident_number, body, created_by="api_user", comment_type="additional_comments"):
    """Persist a comment and bump the parent incident's updated_on."""
    key = incident_number.upper()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    comment = {
        "sys_id": _next_comment_id(),
        "element_id": key,
        "created_on": now_iso,
        "created_by": created_by,
        "body": body,
        "type": comment_type,
    }
    comments_db.setdefault(key, []).append(comment)
    if key in incidents_db:
        incidents_db[key]["updated_on"] = now_iso
        incidents_db[key]["updated_by"] = created_by
    _persist()
    return comment


# Load any state left by a previous pod before serving.
_restore()


# --- Frontend ---
@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, 'index.html')


# --- Config ---
@app.route('/api/v1/config', methods=['GET'])
def get_config():
    return jsonify({"demo_user_name": DEMO_USER_NAME})


@app.route('/api/v1/health', methods=['GET'])
def health_check():
    return jsonify({"status": "UP"}), 200


# --- Incident Stats ---
@app.route('/api/v1/incidents/stats', methods=['GET'])
def get_incident_stats():
    now = datetime.datetime.now(datetime.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - datetime.timedelta(days=7)
    thirty_days_ago = now - datetime.timedelta(days=30)

    all_incidents = list(incidents_db.values())
    open_incidents = [i for i in all_incidents if i['state'].lower() in OPEN_STATES]

    opened_today = [i for i in all_incidents
                    if datetime.datetime.fromisoformat(i['opened_at']) >= today_start]
    unassigned = [i for i in open_incidents if not i.get('assignment_group')]
    overdue = [i for i in open_incidents
               if i.get('due_date') and datetime.datetime.fromisoformat(i['due_date']) < now]
    not_updated_7d = [i for i in open_incidents
                      if datetime.datetime.fromisoformat(i['updated_on']) < seven_days_ago]
    open_older_30d = [i for i in open_incidents
                      if datetime.datetime.fromisoformat(i['opened_at']) < thirty_days_ago]

    open_by_priority = {}
    for inc in open_incidents:
        p = inc.get('priority', 'Unknown')
        open_by_priority[p] = open_by_priority.get(p, 0) + 1

    older_30_by_priority = {}
    for inc in open_older_30d:
        p = inc.get('priority', 'Unknown')
        older_30_by_priority[p] = older_30_by_priority.get(p, 0) + 1

    open_by_assignment_group = {}
    for inc in open_incidents:
        g = inc.get('assignment_group') or 'Unassigned'
        open_by_assignment_group[g] = open_by_assignment_group.get(g, 0) + 1

    by_state = {}
    for inc in all_incidents:
        s = inc.get('state', 'Unknown')
        by_state[s] = by_state.get(s, 0) + 1

    return jsonify({
        "result": {
            "incidents_opened_today": len(opened_today),
            "unassigned_incidents": len(unassigned),
            "overdue_incidents": len(overdue),
            "open_incidents": len(open_incidents),
            "not_updated_7_days": len(not_updated_7d),
            "open_older_30_days": len(open_older_30d),
            "open_by_priority": open_by_priority,
            "older_30_by_priority": older_30_by_priority,
            "open_by_assignment_group": open_by_assignment_group,
            "by_state": by_state,
        }
    })


# --- Incident Endpoints ---
@app.route('/api/v1/incidents', methods=['GET'])
def get_incidents():
    query_params = request.args
    limit = int(query_params.get('limit', 100))
    offset = int(query_params.get('offset', 0))

    filtered = list(incidents_db.values())

    if 'state' in query_params:
        states = [s.strip().lower() for s in query_params['state'].split(',')]
        filtered = [i for i in filtered if i.get('state', '').lower() in states]
    if 'priority' in query_params:
        filtered = [i for i in filtered if i.get('priority', '').startswith(query_params['priority'])]
    if 'assignment_group' in query_params:
        filtered = [i for i in filtered if i.get('assignment_group', '').lower() == query_params['assignment_group'].lower()]
    if 'caller_id' in query_params:
        filtered = [i for i in filtered if i.get('caller_id', '').lower() == query_params['caller_id'].lower()]
    if 'category' in query_params:
        filtered = [i for i in filtered if i.get('category', '').lower() == query_params['category'].lower()]
    if 'parent_incident' in query_params:
        parent_key = query_params['parent_incident'].upper()
        filtered = [
            i for i in filtered
            if (i.get('parent_incident') or '').upper() == parent_key
        ]
    # Exact CMDB CI match (AO lifecycle: gitlab_path stamped on child create).
    if 'cmdb_ci' in query_params:
        ci = query_params['cmdb_ci']
        filtered = [i for i in filtered if (i.get('cmdb_ci') or '') == ci]
    # Tenant guid — prefer dedicated field; fall back to description text.
    if 'guid' in query_params:
        g = query_params['guid']
        filtered = [
            i for i in filtered
            if (i.get('guid') or '') == g
            or f'guid: {g}' in (i.get('description') or '')
            or f'guid={g}' in (i.get('description') or '')
        ]
    if 'opened_today' in query_params:
        now = datetime.datetime.now(datetime.timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        filtered = [i for i in filtered if datetime.datetime.fromisoformat(i['opened_at']) >= today_start]
    if 'open_only' in query_params:
        filtered = [i for i in filtered if i['state'].lower() in OPEN_STATES]
    if 'not_updated_days' in query_params:
        days = int(query_params['not_updated_days'])
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        filtered = [i for i in filtered if datetime.datetime.fromisoformat(i['updated_on']) < cutoff]
        if 'open_only' not in query_params:
            filtered = [i for i in filtered if i['state'].lower() in OPEN_STATES]
    if 'older_than_days' in query_params:
        days = int(query_params['older_than_days'])
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        filtered = [i for i in filtered if datetime.datetime.fromisoformat(i['opened_at']) < cutoff]
        if 'open_only' not in query_params:
            filtered = [i for i in filtered if i['state'].lower() in OPEN_STATES]

    sort_by = query_params.get('sort_by', 'opened_at')
    sort_order = query_params.get('sort_order', 'desc')
    filtered.sort(key=lambda x: x.get(sort_by, x.get('opened_at', '')), reverse=(sort_order == 'desc'))

    paginated = filtered[offset:offset + limit]
    return jsonify({"result": paginated, "total_records": len(filtered), "limit": limit, "offset": offset})


@app.route('/api/v1/incidents/<string:incident_number>', methods=['GET'])
def get_incident(incident_number):
    key = incident_number.upper()
    incident = incidents_db.get(key)
    if not incident:
        return jsonify({"error": "Incident not found"}), 404
    result = dict(incident)
    result["comments"] = list(comments_db.get(key, []))
    # Always expose parent/child linkage for AO parent+child remediations.
    parent = (result.get("parent_incident") or "").upper()
    result["parent_incident"] = parent or None
    children = [
        i["number"]
        for i in incidents_db.values()
        if (i.get("parent_incident") or "").upper() == key
    ]
    result["child_incidents"] = sorted(children)
    return jsonify({"result": result})


@app.route('/api/v1/incidents/<string:incident_number>/comments', methods=['GET'])
def list_comments(incident_number):
    key = incident_number.upper()
    if key not in incidents_db:
        return jsonify({"error": "Incident not found"}), 404
    return jsonify({"result": list(comments_db.get(key, [])), "total_records": len(comments_db.get(key, []))})


@app.route('/api/v1/incidents/<string:incident_number>/comments', methods=['POST'])
def create_comment(incident_number):
    key = incident_number.upper()
    if key not in incidents_db:
        return jsonify({"error": "Incident not found"}), 404
    if not request.json:
        return jsonify({"error": "Request body cannot be empty"}), 400

    body = (
        request.json.get("body")
        or request.json.get("text")
        or request.json.get("comment")
        or request.json.get("value")
        or request.json.get("work_notes")
        or request.json.get("additional_comments")
    )
    if not body or not str(body).strip():
        return jsonify({"error": "Missing required field: body"}), 400

    comment = _append_comment(
        key,
        str(body).strip(),
        created_by=request.json.get("created_by", "api_user"),
        comment_type=request.json.get("type", "additional_comments"),
    )
    return jsonify({"result": comment}), 201


@app.route('/api/v1/incidents', methods=['POST'])
def create_incident():
    if not request.json or 'short_description' not in request.json or 'caller_id' not in request.json:
        return jsonify({"error": "Missing required fields: short_description, caller_id"}), 400
    if 'description' not in request.json:
        return jsonify({"error": "Missing required field: description"}), 400

    new_number = get_next_number("INC", incidents_db.keys())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    parent_raw = request.json.get("parent_incident") or request.json.get("parent") or ""
    parent_incident = str(parent_raw).strip().upper() if parent_raw else ""
    if parent_incident and parent_incident not in incidents_db:
        return jsonify({"error": f"Parent incident not found: {parent_incident}"}), 400

    new_incident = {
        "number": new_number,
        "state": request.json.get("state", "New"),
        "short_description": request.json['short_description'],
        "assignment_group": request.json.get("assignment_group", "Service Desk"),
        "priority": request.json.get("priority", "4 - Low"),
        "impact": request.json.get("impact", "3 - Low"),
        "channel": request.json.get("channel", "Self-service"),
        "category": request.json.get("category", "Unknown"),
        "subcategory": request.json.get("subcategory", ""),
        "cmdb_ci": request.json.get("cmdb_ci", ""),
        "guid": str(request.json.get("guid") or "").strip(),
        "caller_id": request.json['caller_id'],
        "opened_at": now_iso,
        "sys_created_on": now_iso,
        "created_by": request.json.get("created_by", "api_user"),
        "opened_by": request.json.get("opened_by", request.json['caller_id']),
        "description": request.json['description'],
        "escalation": request.json.get("escalation", "-- None --"),
        "updated_on": now_iso,
        "updated_by": "api_user",
        "parent_incident": parent_incident or None,
    }

    if request.json.get("state", "").lower() in ["resolved", "closed"] and 'resolution_notes' in request.json:
        new_incident["resolution_notes"] = request.json["resolution_notes"]
        new_incident["resolution_code"] = request.json.get("resolution_code", "Solved")
        new_incident["closed_at"] = now_iso
        new_incident["resolved_by"] = request.json.get("resolved_by", "api_user")

    incidents_db[new_number] = new_incident
    comments_db[new_number] = []
    _persist()

    # Optional initial comment on create (e.g. remediation context)
    initial = request.json.get("comment") or request.json.get("additional_comments")
    if initial:
        _append_comment(
            new_number,
            str(initial).strip(),
            created_by=request.json.get("created_by", "api_user"),
        )

    result = dict(new_incident)
    result["comments"] = list(comments_db.get(new_number, []))
    return jsonify({"result": result}), 201


@app.route('/api/v1/incidents/<string:incident_number>', methods=['PUT', 'PATCH'])
def update_incident(incident_number):
    key = incident_number.upper()
    if key not in incidents_db:
        return jsonify({"error": "Incident not found"}), 404
    if not request.json:
        return jsonify({"error": "Request body cannot be empty"}), 400

    inc = incidents_db[key]
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Journal fields posted via PATCH become comments (ServiceNow-style)
    journal = {}
    for jk in ("additional_comments", "work_notes", "comment"):
        if jk in request.json and request.json[jk]:
            journal[jk] = request.json[jk]

    immutable = {"number", "opened_at", "caller_id", "sys_created_on", "comments"}
    for k, v in request.json.items():
        if k not in immutable and k not in ("additional_comments", "work_notes", "comment"):
            inc[k] = v

    for jk, text in journal.items():
        ctype = "work_notes" if jk == "work_notes" else "additional_comments"
        _append_comment(key, str(text).strip(), created_by="api_user_update", comment_type=ctype)

    inc["updated_on"] = now_iso
    inc["updated_by"] = "api_user_update"

    if inc.get("state", "").lower() in ["resolved", "closed"]:
        inc.setdefault("closed_at", now_iso)
        inc.setdefault("resolution_notes", "Resolved via API.")
        inc.setdefault("resolution_code", "Solved")
        inc.setdefault("resolved_by", "api_user_resolve")

    _persist()
    result = dict(inc)
    result["comments"] = list(comments_db.get(key, []))
    return jsonify({"result": result})


# --- Service Request Endpoints ---
@app.route('/api/v1/requests', methods=['GET'])
def get_service_requests():
    query_params = request.args
    limit = int(query_params.get('limit', 10))
    offset = int(query_params.get('offset', 0))

    filtered = list(requests_db.values())

    if 'state' in query_params:
        filtered = [r for r in filtered if r.get('state', '').lower() == query_params['state'].lower()]
    if 'requested_by' in query_params:
        filtered = [r for r in filtered if r.get('requested_by', '').lower() == query_params['requested_by'].lower()]
    if 'assignment_group' in query_params:
        filtered = [r for r in filtered if r.get('assignment_group', '').lower() == query_params['assignment_group'].lower()]

    sort_by = query_params.get('sort_by', 'opened_at')
    sort_order = query_params.get('sort_order', 'desc')
    filtered.sort(key=lambda x: x.get(sort_by, x.get('opened_at', '')), reverse=(sort_order == 'desc'))

    paginated = filtered[offset:offset + limit]
    return jsonify({"result": paginated, "total_records": len(filtered), "limit": limit, "offset": offset})


@app.route('/api/v1/requests/<string:request_number>', methods=['GET'])
def get_service_request(request_number):
    req = requests_db.get(request_number.upper())
    if req:
        return jsonify({"result": req})
    return jsonify({"error": "Service Request not found"}), 404


@app.route('/api/v1/requests', methods=['POST'])
def create_service_request():
    if not request.json or 'short_description' not in request.json or 'requested_for' not in request.json:
        return jsonify({"error": "Missing required fields: short_description, requested_for"}), 400

    new_number = get_next_number("REQ", requests_db.keys())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    new_req = {
        "number": new_number,
        "state": request.json.get("state", "Submitted"),
        "stage": request.json.get("stage", "Requested"),
        "short_description": request.json['short_description'],
        "assignment_group": request.json.get("assignment_group", "Service Catalog Fulfillment"),
        "priority": request.json.get("priority", "4 - Low"),
        "opened_at": now_iso,
        "requested_by": request.json.get("requested_by", "api_user"),
        "requested_for": request.json['requested_for'],
        "item_details": request.json.get("item_details", {}),
        "description": request.json.get("description", ""),
        "approval": request.json.get("approval", "Not Yet Requested"),
        "updated_on": now_iso,
        "updated_by": "api_user",
    }

    if new_req["state"].lower() in ["closed", "fulfilled", "completed"]:
        new_req["closed_at"] = now_iso
        new_req["stage"] = request.json.get("stage", "Completed")

    requests_db[new_number] = new_req
    return jsonify({"result": new_req}), 201


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
