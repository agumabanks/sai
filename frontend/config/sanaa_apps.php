<?php

return [
    /*
    |--------------------------------------------------------------------------
    | Registered Apps for SanaaDoctor Monitoring
    |--------------------------------------------------------------------------
    |
    | Each app monitored by SanaaDoctor must be listed here with its health
    | endpoint, optional heal endpoint, API secret env key, and thresholds.
    |
    */

    'apps' => [
        // ── Core Sanaa Ecosystem ───────────────────────────────────────────

        'soko24' => [
            'key' => 'soko24',
            'name' => 'Soko 24',
            'health_url' => 'https://soko24.co/api/health',
            'heal_url' => 'https://soko24.co/api/heal',
            'api_secret' => env('SOKO24_DOCTOR_SECRET'),
            'tenant' => null,
            'type' => 'ecommerce',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => 60,
            ],
        ],

        'baraka24' => [
            'key' => 'baraka24',
            'name' => 'Baraka 24',
            'health_url' => 'https://baraka.sanaa.co/api/health',
            'heal_url' => 'https://baraka.sanaa.co/api/heal',
            'api_secret' => env('BARAKA24_DOCTOR_SECRET'),
            'tenant' => null,
            'type' => 'logistics',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => 60,
            ],
        ],

        'baraka24_drc' => [
            'key' => 'baraka24_drc',
            'name' => 'Baraka 24 DRC',
            'health_url' => 'https://drc.baraka24.co/api/health',
            'heal_url' => 'https://drc.baraka24.co/api/heal',
            'api_secret' => env('BARAKA24_DRC_DOCTOR_SECRET'),
            'tenant' => 'drc_client',
            'type' => 'logistics',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => 60,
            ],
        ],

        'sanaa_finance' => [
            'key' => 'sanaa_finance',
            'name' => 'Sanaa Finance',
            'health_url' => 'https://finance.sanaa.ug/api/health',
            'heal_url' => 'https://finance.sanaa.ug/api/heal',
            'api_secret' => env('SANAA_FINANCE_DOCTOR_SECRET'),
            'tenant' => null,
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'fx_sanaa' => [
            'key' => 'fx_sanaa',
            'name' => 'FX Sanaa',
            'health_url' => 'https://fx.sanaa.co/api/health',
            'heal_url' => 'https://fx.sanaa.co/api/heal',
            'api_secret' => env('FX_SANAA_DOCTOR_SECRET'),
            'tenant' => null,
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'antigravity' => [
            'key' => 'antigravity',
            'name' => 'Antigravity AI',
            'health_url' => env('APP_URL', 'https://ai.sanaa.co').'/health',
            'heal_url' => env('APP_URL', 'https://ai.sanaa.co').'/health/heal',
            'api_secret' => env('ANTIGRAVITY_DOCTOR_SECRET', env('SANAA_DOCTOR_SECRET')),
            'tenant' => null,
            'type' => 'platform',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        // ── Additional Production Apps ────────────────────────────────────

        'cards' => [
            'key' => 'cards',
            'name' => 'Cards Sanaa',
            'health_url' => 'https://cards.sanaa.ug/api/health',
            'heal_url' => 'https://cards.sanaa.ug/api/heal',
            'api_secret' => env('CARDS_DOCTOR_SECRET'),
            'tenant' => null,
            'type' => 'platform',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'procurement' => [
            'key' => 'procurement',
            'name' => 'Procurement UNDPF',
            'health_url' => 'https://procurement.undpf.org/api/health',
            'heal_url' => 'https://procurement.undpf.org/api/heal',
            'api_secret' => env('PROCUREMENT_DOCTOR_SECRET'),
            'tenant' => null,
            'type' => 'platform',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'tickets' => [
            'key' => 'tickets',
            'name' => 'Tickets Sanaa',
            'health_url' => 'https://tickets.sanaa.ug/api/health',
            'heal_url' => 'https://tickets.sanaa.ug/api/heal',
            'api_secret' => env('TICKETS_DOCTOR_SECRET'),
            'tenant' => null,
            'type' => 'support',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'myportal' => [
            'key' => 'myportal',
            'name' => 'MyPortal KYA',
            'health_url' => 'https://myportal.kya.ac.ug/api/health',
            'heal_url' => 'https://myportal.kya.ac.ug/api/heal',
            'api_secret' => env('MYPORTAL_DOCTOR_SECRET'),
            'tenant' => null,
            'type' => 'education',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        // ── Mbalala (SACCO) Network ───────────────────────────────────────

        'bukuya' => [
            'key' => 'bukuya',
            'name' => 'Bukuya SACCO',
            'health_url' => 'https://bukuya.sanaa.ug/api/health',
            'heal_url' => 'https://bukuya.sanaa.ug/api/heal',
            'api_secret' => env('BUKUYA_DOCTOR_SECRET'),
            'tenant' => 'bukuya',
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'kijura' => [
            'key' => 'kijura',
            'name' => 'Kijura SACCO',
            'health_url' => 'https://kijura.sanaa.ug/api/health',
            'heal_url' => 'https://kijura.sanaa.ug/api/heal',
            'api_secret' => env('KIJURA_DOCTOR_SECRET'),
            'tenant' => 'kijura',
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'kasawo' => [
            'key' => 'kasawo',
            'name' => 'Kasawo SACCO',
            'health_url' => 'https://kasawo.sanaa.ug/api/health',
            'heal_url' => 'https://kasawo.sanaa.ug/api/heal',
            'api_secret' => env('KASAWO_DOCTOR_SECRET'),
            'tenant' => 'kasawo',
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'mityana' => [
            'key' => 'mityana',
            'name' => 'Mityana SACCO',
            'health_url' => 'https://mityana.sanaa.ug/api/health',
            'heal_url' => 'https://mityana.sanaa.ug/api/heal',
            'api_secret' => env('MITYANA_DOCTOR_SECRET'),
            'tenant' => 'mityana',
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'kyaliwajjala' => [
            'key' => 'kyaliwajjala',
            'name' => 'Kyaliwajjala SACCO',
            'health_url' => 'https://kyaliwajjala.sanaa.ug/api/health',
            'heal_url' => 'https://kyaliwajjala.sanaa.ug/api/heal',
            'api_secret' => env('KYALIWAJJALA_DOCTOR_SECRET'),
            'tenant' => 'kyaliwajjala',
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'mslink' => [
            'key' => 'mslink',
            'name' => 'MS Link SACCO',
            'health_url' => 'https://mslink.sanaa.ug/api/health',
            'heal_url' => 'https://mslink.sanaa.ug/api/heal',
            'api_secret' => env('MSLINK_DOCTOR_SECRET'),
            'tenant' => 'mslink',
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'kalamba' => [
            'key' => 'kalamba',
            'name' => 'Kalamba SACCO',
            'health_url' => 'https://kalamba.sanaa.ug/api/health',
            'heal_url' => 'https://kalamba.sanaa.ug/api/heal',
            'api_secret' => env('KALAMBA_DOCTOR_SECRET'),
            'tenant' => 'kalamba',
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],

        'bweyale' => [
            'key' => 'bweyale',
            'name' => 'Bweyale SACCO',
            'health_url' => 'https://bweyale.sanaa.ug/api/health',
            'heal_url' => 'https://bweyale.sanaa.ug/api/heal',
            'api_secret' => env('BWEYALE_DOCTOR_SECRET'),
            'tenant' => 'bweyale',
            'type' => 'finance',
            'thresholds' => [
                'queue_depth_max' => 50,
                'failed_jobs_1h_max' => 5,
                'db_latency_ms_max' => 300,
                'error_rate_1h_max' => 5.0,
                'last_order_stale_minutes' => null,
            ],
        ],
    ],
];
