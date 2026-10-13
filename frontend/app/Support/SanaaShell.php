<?php

namespace App\Support;

use App\Models\SanaaHealthLog;
use App\Services\SanaaEngineService;
use Illuminate\Support\Facades\DB;

class SanaaShell
{
    public static function registry(): array
    {
        $modules = collect(SanaaModules::all())->keyBy('id');

        return [
            'modules' => $modules->values()->all(),
            'shortcuts' => self::shortcuts(),
            'features' => SanaaOsFeatures::all(),
            'os_url' => url('/'),
            'admin_url' => url('/'),
            'doctor_url' => route('filament.admin.pages.sanaa-doctor'),
            'device_army_url' => route('filament.admin.pages.device-army-dashboard'),
        ];
    }

    public static function shortcuts(): array
    {
        return collect(SanaaOsFeatures::all())
            ->filter(fn (array $f): bool => (bool) ($f['shortcut'] ?? $f['desktop'] ?? $f['pinned'] ?? false))
            ->sortBy([
                fn (array $f) => (int) ($f['sort'] ?? 100),
                fn (array $f) => $f['label'] ?? '',
            ])
            ->groupBy('module')
            ->map(fn ($items, $moduleId) => [
                'module' => $moduleId,
                'module_label' => $items->first()['module_label'] ?? $moduleId,
                'module_accent' => $items->first()['module_accent'] ?? '#6366f1',
                'items' => $items->map(fn (array $f): array => self::shortcutItem($f))->values()->all(),
            ])
            ->values()
            ->all();
    }

    public static function quickLaunch(): array
    {
        return collect(SanaaOsFeatures::all())
            ->filter(fn (array $f): bool => (bool) ($f['quick_launch'] ?? $f['pinned'] ?? false))
            ->sortBy(fn (array $f) => (int) ($f['sort'] ?? 100))
            ->take((int) config('sanaa_os_features.dock.max_shortcuts', 12))
            ->map(fn (array $f): array => self::shortcutItem($f))
            ->values()
            ->all();
    }

    public static function ecosystemApps(): array
    {
        $configured = config('sanaa_apps.apps', []);

        $subquery = SanaaHealthLog::query()
            ->select('app', DB::raw('MAX(created_at) as max_created_at'))
            ->groupBy('app');

        $logs = SanaaHealthLog::query()
            ->from('sanaa_health_log as main')
            ->joinSub($subquery, 'latest', function ($join): void {
                $join->on('main.app', '=', 'latest.app')
                    ->on('main.created_at', '=', 'latest.max_created_at');
            })
            ->select('main.*')
            ->get()
            ->keyBy('app');

        return collect($configured)->map(function (array $app, string $key) use ($logs): array {
            $log = $logs->get($key);
            $status = $log?->status ?? 'unknown';
            $healthUrl = $app['health_url'] ?? null;

            $healUrl = $app['heal_url'] ?? null;

            return [
                'key' => $key,
                'name' => $app['name'] ?? $key,
                'type' => $app['type'] ?? 'platform',
                'tenant' => $app['tenant'] ?? null,
                'status' => $status,
                'score' => $log?->score,
                'checked_at' => $log?->created_at?->toIso8601String(),
                'health_url' => $healthUrl,
                'heal_url' => $healUrl,
                'can_heal' => ! empty($healUrl),
                'external_url' => $healthUrl ? preg_replace('#/api/health$#', '', $healthUrl) : null,
                'doctor_url' => route('filament.admin.pages.sanaa-doctor'),
            ];
        })->values()->all();
    }

    public static function ecosystemSummary(array $apps): array
    {
        $collection = collect($apps);

        return [
            'total' => $collection->count(),
            'healthy' => $collection->where('status', 'healthy')->count(),
            'degraded' => $collection->where('status', 'degraded')->count(),
            'critical' => $collection->where('status', 'critical')->count(),
            'unknown' => $collection->where('status', 'unknown')->count(),
        ];
    }

    public static function liveData(?array $metrics = null): array
    {
        $engine = app(SanaaEngineService::class);
        $status = $metrics ? null : $engine->getStatus();
        $metrics ??= self::metricsFromStatus($status);
        $apps = self::ecosystemApps();
        $deviceStats = self::deviceStats($engine);
        $devices = self::connectedDevices($engine);

        return [
            'generated_at' => now()->toIso8601String(),
            'metrics' => $metrics,
            'ecosystem' => [
                'summary' => self::ecosystemSummary($apps),
                'apps' => $apps,
            ],
            'devices' => [
                'stats' => $deviceStats,
                'connected' => $devices,
            ],
            'soko' => $engine->getSokoPulse(),
            'dock' => config('sanaa_os_features.dock', []),
        ];
    }

    public static function forJson(): array
    {
        return [
            ...self::registry(),
            'quick_launch' => self::quickLaunch(),
            'ecosystem_apps' => self::ecosystemApps(),
            'dock' => config('sanaa_os_features.dock', []),
            'live' => self::liveData(),
            'mission' => [
                'title' => 'Sanaa OS',
                'tagline' => 'Your platform command center',
                'description' => 'Operate the Sanaa ecosystem from one account — web, desktop, and mobile. Mini-apps and business tools arrive as the platform grows.',
                'phase' => 'operator',
            ],
            'permissions' => SanaaOsPermissions::toJson(),
        ];
    }

    public static function metricsFromStatus(array $status): array
    {
        $server = $status['server'] ?? [];
        $cpu = $server['cpu']['percent'] ?? 0;
        $memory = $server['memory']['percent'] ?? 0;
        $disk = $server['disk'] ?? [];

        return [
            'cpu' => round((float) $cpu, 1),
            'memory' => round((float) $memory, 1),
            'disk' => round((float) ($disk['percent'] ?? 0), 1),
            'disk_free_gb' => round((float) ($disk['free_gb'] ?? 0), 1),
            'alerts' => (int) ($status['alerts']['unacknowledged'] ?? 0),
            'brain' => $status['channels']['active_provider'] ?? ($status['brain']['active_provider'] ?? 'auto'),
            'overall_status' => $server['overall_status'] ?? 'unknown',
            'services_active' => count(array_filter($server['services'] ?? [], fn ($s) => $s === 'active')),
            'services_total' => count($server['services'] ?? []),
        ];
    }

    private static function deviceStats(SanaaEngineService $engine): array
    {
        $stats = $engine->getDeviceArmyStats();

        return [
            'total' => (int) ($stats['total_devices'] ?? $stats['total'] ?? 0),
            'online' => (int) ($stats['online_devices'] ?? $stats['online'] ?? $stats['online_count'] ?? 0),
            'busy' => (int) ($stats['busy'] ?? 0),
            'offline' => (int) ($stats['offline_devices'] ?? $stats['offline'] ?? 0),
        ];
    }

    private static function connectedDevices(SanaaEngineService $engine): array
    {
        $payload = $engine->getDeviceArmyDevices(8);

        return collect($payload['devices'] ?? [])
            ->take(8)
            ->map(fn (array $device): array => [
                'id' => $device['device_id'] ?? '',
                'name' => $device['display_name'] ?? $device['codename'] ?? 'Device',
                'status' => $device['status'] ?? 'offline',
                'role' => $device['worker_role'] ?? 'worker',
                'model' => $device['device_model'] ?? null,
                'battery' => $device['battery_health'] ?? null,
                'storage_mb' => $device['storage_mb'] ?? null,
                'ram_mb' => $device['ram_mb'] ?? null,
                'last_seen' => $device['last_heartbeat'] ?? null,
                'url' => route('filament.admin.pages.device-army-dashboard'),
            ])
            ->values()
            ->all();
    }

    private static function shortcutItem(array $feature): array
    {
        $isNative = ($feature['type'] ?? '') === 'native';
        $appId = $isNative
            ? ($feature['native_app'] ?? $feature['id'])
            : 'panel-'.$feature['id'];

        return [
            'id' => $feature['id'],
            'label' => $feature['label'] ?? $feature['id'],
            'description' => $feature['description'] ?? ($feature['module_label'] ?? ''),
            'module' => $feature['module'] ?? null,
            'module_label' => $feature['module_label'] ?? null,
            'accent' => $feature['module_accent'] ?? '#6366f1',
            'icon' => $feature['icon'] ?? 'brain',
            'type' => $feature['type'] ?? 'filament',
            'app_id' => $appId,
            'url' => $feature['url'] ?? null,
            'path' => $feature['path'] ?? null,
            'external' => (bool) ($feature['external'] ?? false),
        ];
    }
}
