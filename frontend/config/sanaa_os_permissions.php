<?php

return [
    /*
    |--------------------------------------------------------------------------
    | Sanaa OS — Role permissions (operator-first platform)
    |--------------------------------------------------------------------------
    |
    | Phase 1: platform operators on ai.sanaa.co
    | Future: extend per-app for Sanaa ecosystem mini-apps (Soko, Finance, etc.)
    |
    */

    'roles' => [
        'admin' => [
            'label' => 'Administrator',
            'description' => 'Full platform control — users, devices, settings, all apps',
            'level' => 3,
        ],
        'operator' => [
            'label' => 'Operator',
            'description' => 'Run and monitor the platform — no user administration',
            'level' => 2,
        ],
        'viewer' => [
            'label' => 'Viewer',
            'description' => 'Read-only monitoring and search',
            'level' => 1,
        ],
        'seller' => [
            'label' => 'Seller',
            'description' => 'Seller OS and storefront — no platform operations',
            'level' => 1,
        ],
    ],

    'apps' => [
        'operatorhome' => ['admin', 'operator', 'viewer'],
        'terminal' => ['admin', 'operator'],
        'filemanager' => ['admin', 'operator', 'viewer'],
        'kabati' => ['admin', 'operator', 'viewer'],
        'settings' => ['admin', 'operator', 'viewer'],
        'sanaadevices' => ['admin', 'operator', 'viewer'],
        'sanaachat' => ['admin', 'operator', 'viewer'],
        'sanaacontacts' => ['admin', 'operator', 'viewer'],
        'systemmonitor' => ['admin', 'operator', 'viewer'],
        'networkmonitor' => ['admin', 'operator', 'viewer'],
        'usermanager' => ['admin'],
        'adminportal' => ['admin', 'operator'],
        'skillslab' => ['admin', 'operator'],
        'intelligencearchive' => ['admin', 'operator', 'viewer'],
        'crashviewer' => ['admin', 'operator'],
        'calendar' => ['admin', 'operator', 'viewer'],
        'sanaanotes' => ['admin', 'operator', 'viewer'],
        'browser' => ['admin', 'operator', 'viewer'],
        'braingraph' => ['admin', 'operator', 'viewer'],
        'papers' => ['admin', 'operator', 'viewer'],
        'markdowneditor' => ['admin', 'operator', 'viewer'],
        'memoryviewer' => ['admin', 'operator', 'viewer'],
        'newsintelligence' => ['admin', 'operator', 'viewer'],
        'sokocommand' => ['admin', 'operator', 'seller', 'viewer'],
        'calculator' => ['admin', 'operator', 'viewer'],
        'texteditor' => ['admin', 'operator', 'viewer'],
    ],

    'settings_panes' => [
        'general' => ['admin', 'operator', 'viewer'],
        'network' => ['admin', 'operator', 'viewer'],
        'display' => ['admin', 'operator', 'viewer'],
        'menubar' => ['admin', 'operator'],
        'desktop_dock' => ['admin', 'operator'],
        'wallpaper' => ['admin', 'operator', 'viewer'],
        'sound' => ['admin', 'operator', 'viewer'],
        'mode' => ['admin', 'operator'],
        'notifications' => ['admin', 'operator'],
        'control_center' => ['admin', 'operator'],
        'security' => ['admin'],
        'users' => ['admin'],
        'apps' => ['admin', 'operator'],
        'sanaa_devices' => ['admin', 'operator', 'viewer'],
        'sanaa_cloud' => ['admin', 'operator', 'viewer'],
        'brain' => ['admin', 'operator'],
        'soko' => ['admin', 'operator'],
        'media' => ['admin', 'operator', 'viewer'],
        'development' => ['admin', 'operator'],
    ],

    'panel_prefix' => [
        'panel-' => ['admin', 'operator', 'viewer'],
        'panel-usermanagement' => ['admin'],
        'panel-sessionpolicy' => ['admin'],
        'panel-auditlog' => ['admin'],
    ],

    'actions' => [
        'users.create' => ['admin'],
        'users.edit' => ['admin'],
        'users.delete' => ['admin'],
        'users.restore' => ['admin'],
        'devices.pair' => ['admin', 'operator'],
        'devices.command' => ['admin', 'operator'],
        'devices.revoke' => ['admin'],
        'settings.export' => ['admin'],
        'settings.reset' => ['admin'],
        'system.command' => ['admin', 'operator'],
    ],
];
