# Water Regulator Dashboard (Django + Gentelella)

This is a starter Django dashboard for the **water regulator** side of your smart water metering system.
It already uses the **Gentelella layout structure** and loads **Gentelella CSS/JS from CDN** so you can run it quickly.

## Pages included
- Dashboard home
- Meters
- Readings
- Alerts
- Reports

## Quick start
1. Create a virtual environment
2. Install requirements
3. Run migrations
4. Start the server

### Commands
```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open:
- http://127.0.0.1:8000/

## MTN MoMo sandbox

Subscribe to the **Collections** product in the MTN MoMo Developer Portal and
copy its primary subscription key. Provision sandbox credentials:

```powershell
python manage.py setup_mtn_sandbox `
  --subscription-key "YOUR_COLLECTIONS_PRIMARY_KEY" `
  --callback-host "192.168.1.78"
```

Set the three values printed by the command before starting Django:

```powershell
$env:MTN_MOMO_SUBSCRIPTION_KEY="..."
$env:MTN_MOMO_API_USER="..."
$env:MTN_MOMO_API_KEY="..."
python manage.py runserver 0.0.0.0:8000
```

The sandbox uses MTN test MSISDN `56733123453` and currency `EUR`. It exercises
the real API flow but does not charge real money. Production credentials,
currency, callback host and target environment must be supplied separately.

## Notes
- The current official Gentelella project is a modern Bootstrap 5 template distributed with a Vite-based workflow.
- This starter intentionally uses CDN-hosted Gentelella `custom.min.css` and `custom.min.js` so it is easier to drop into Django immediately.
- The sample pages currently use mock dashboard data inside `dashboard/views.py`.
- You can later connect the pages to your real `Meter`, `Reading`, and `Alert` tables.

## Next edits you may want
- add login
- connect real database records
- add charts per zone
- add export to PDF/Excel
- add mobile-app API endpoints for users


##################
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/constants/app_colors.dart';
import '../../models/meter_model.dart';
import '../../services/api_service.dart';
import '../../widgets/action_tile.dart';
import '../../widgets/gradient_card.dart';
import '../../widgets/stat_card.dart';
import '../billing/bills_screen.dart';
import '../reports/reports_screen.dart';
import '../support/support_screen.dart';
import '../valve/valve_control_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {

  late Future<MeterModel> meterFuture;

  String fullName = 'User';
  String meterCode = '';

  @override
  void initState() {
    super.initState();

    meterFuture = ApiService().fetchLatestMeter();

    loadUserName();
  }

  Future<void> loadUserName() async {

    final prefs =
        await SharedPreferences.getInstance();

    setState(() {

      fullName =
          prefs.getString('full_name') ??
          'User';

      meterCode =
          prefs.getString('meter_code') ??
          'No Meter';

    });
  }

  void refreshMeter() {
    setState(() {
      meterFuture = ApiService().fetchLatestMeter();
    });
  }

  @override
  Widget build(BuildContext context) {

    return FutureBuilder<MeterModel>(

      future: meterFuture,

      builder: (context, snapshot) {

        if (snapshot.connectionState ==
            ConnectionState.waiting) {

          return const Scaffold(
            body: Center(
              child: CircularProgressIndicator(),
            ),
          );
        }

        if (snapshot.hasError) {

          return Scaffold(
            body: Center(
              child: Text(
                'Failed to load meter data\n${snapshot.error}',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }

        final meter = snapshot.data!;

        return SafeArea(

          child: RefreshIndicator(

            onRefresh: () async {
              refreshMeter();
            },

            child: SingleChildScrollView(

              physics:
                  const AlwaysScrollableScrollPhysics(),

              padding:
                  const EdgeInsets.fromLTRB(
                20,
                18,
                20,
                100,
              ),

              child: Column(

                crossAxisAlignment:
                    CrossAxisAlignment.start,

                children: [

                  Row(

                    children: [

                      const CircleAvatar(
                        radius: 25,
                        backgroundColor:
                            AppColors.blue,
                        child: Icon(
                          Icons.person,
                          color: Colors.white,
                        ),
                      ),

                      const SizedBox(width: 12),

                      Expanded(

                        child: Column(

                          crossAxisAlignment:
                              CrossAxisAlignment.start,

                          children: [

                            const Text(
                              'Welcome back,',
                              style: TextStyle(
                                color: Colors.black54,
                              ),
                            ),

                            Text(

                              fullName,

                              maxLines: 1,

                              overflow:
                                  TextOverflow.ellipsis,

                              style: const TextStyle(
                                fontWeight:
                                    FontWeight.w900,
                                fontSize: 18,
                              ),
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(width: 8),

                      const Icon(
                        Icons.qr_code_scanner_rounded,
                        color: AppColors.blue,
                      ),
                    ],
                  ),

                  const SizedBox(height: 24),

                  GradientCard(

                    child: Column(

                      crossAxisAlignment:
                          CrossAxisAlignment.start,

                      children: [

                        Text(
                          '$meterCode • ${meter.status}',
                          style: const TextStyle(
                            color: Colors.white70,
                          ),
                        ),

                        const SizedBox(height: 20),

                        const Text(
                          "Today's Water Usage",
                          style: TextStyle(
                            color: Colors.white70,
                          ),
                        ),

                        const SizedBox(height: 8),

                        Text(
                          '${meter.todayUsage} Litres',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 40,
                            fontWeight:
                                FontWeight.w900,
                          ),
                        ),

                        const SizedBox(height: 18),

                        const LinearProgressIndicator(
                          value: .68,
                          color: Colors.white,
                          backgroundColor:
                              Colors.white24,
                        ),

                        const SizedBox(height: 8),

                        const Text(
                          'Pull down to refresh live reading',
                          style: TextStyle(
                            color: Colors.white70,
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 18),

                  Row(

                    children: [

                      Expanded(
                        child: StatCard(
                          icon:
                              Icons.water_drop_rounded,
                          title: 'Flow Rate',
                          value:
                              '${meter.flowRate} L/min',
                        ),
                      ),

                      const SizedBox(width: 12),

                      Expanded(
                        child: StatCard(
                          icon:
                              Icons.lock_open_rounded,
                          title: 'Valve',
                          value: meter.valveOpen
                              ? 'Open'
                              : 'Closed',
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 24),

                  Row(

                    children: [

                      const Expanded(
                        child: Text(
                          'Quick Actions',
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight:
                                FontWeight.w900,
                          ),
                        ),
                      ),

                      IconButton(
                        onPressed: refreshMeter,
                        icon: const Icon(
                          Icons.refresh_rounded,
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 14),

                  GridView.count(

                    crossAxisCount: 2,

                    shrinkWrap: true,

                    crossAxisSpacing: 12,

                    mainAxisSpacing: 12,

                    physics:
                        const NeverScrollableScrollPhysics(),

                    childAspectRatio: 1.45,

                    children: [

                      ActionTile(

                        icon:
                            Icons.power_settings_new_rounded,

                        title: 'Valve Control',

                        subtitle:
                            'Open or close water',

                        onTap: () {

                          Navigator.push(

                            context,

                            MaterialPageRoute(
                              builder: (_) =>
                                  const ValveControlScreen(),
                            ),
                          );
                        },
                      ),

                      ActionTile(

                        icon:
                            Icons.picture_as_pdf_rounded,

                        title: 'Reports',

                        subtitle:
                            'PDF and Excel',

                        onTap: () {

                          Navigator.push(

                            context,

                            MaterialPageRoute(
                              builder: (_) =>
                                  const ReportsScreen(),
                            ),
                          );
                        },
                      ),

                      ActionTile(

                        icon:
                            Icons.support_agent_rounded,

                        title: 'Support',

                        subtitle:
                            'Report a problem',

                        onTap: () {

                          Navigator.push(

                            context,

                            MaterialPageRoute(
                              builder: (_) =>
                                  const SupportScreen(),
                            ),
                          );
                        },
                      ),

                      ActionTile(

                        icon:
                            Icons.payment_rounded,

                        title: 'Mobile Money',

                        subtitle:
                            'MTN and Airtel',

                        onTap: () {

                          Navigator.push(

                            context,

                            MaterialPageRoute(
                              builder: (_) =>
                                  const BillsScreen(),
                            ),
                          );
                        },
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
