<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Pages\Dashboard as BaseDashboard;

class Dashboard extends BaseDashboard
{
    protected static ?string $navigationIcon = 'heroicon-o-home';

    protected static string $view = 'filament.pages.dashboard';

    public array $systemMetrics = [];

    public function mount()
    {
        $this->refreshMetrics();
    }

    public function refreshMetrics()
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();

        $server = $status['server'] ?? [];
        $cpu = $server['cpu']['percent'] ?? 0;
        $memory = $server['memory']['percent'] ?? 0;
        $disk = $server['disk'] ?? [];
        $alerts = $status['alerts'] ?? [];
        $services = $server['services'] ?? [];
        $uptimeSince = $server['uptime_since'] ?? null;

        // Format uptime as human-readable
        $uptimeText = 'N/A';
        if ($uptimeSince) {
            try {
                $since = \Carbon\Carbon::parse($uptimeSince);
                $diff = $since->diff(now());
                $parts = [];
                if ($diff->days > 0) $parts[] = $diff->days . 'd';
                if ($diff->h > 0) $parts[] = $diff->h . 'h';
                if ($diff->i > 0) $parts[] = $diff->i . 'm';
                $uptimeText = implode(' ', $parts) ?: '< 1m';
            } catch (\Exception $e) {
                $uptimeText = 'N/A';
            }
        }

        // Count active services
        $activeServices = count(array_filter($services, fn($s) => $s === 'active'));
        $totalServices = count($services);

        $this->systemMetrics = [
            'cpu' => round($cpu, 1),
            'cpuStatus' => $server['cpu']['status'] ?? 'ok',
            'cpuCores' => $server['cpu']['cores'] ?? 0,
            'cpuLoad' => $server['cpu']['load_1m'] ?? 0,
            'memory' => round($memory, 1),
            'memoryStatus' => $server['memory']['status'] ?? 'ok',
            'memoryTotal' => round($server['memory']['total_gb'] ?? 0, 1),
            'disk' => round($disk['percent'] ?? 0, 1),
            'diskFree' => round($disk['free_gb'] ?? 0, 1),
            'diskStatus' => $disk['status'] ?? 'ok',
            'uptime' => $uptimeText,
            'alertCount' => $alerts['unacknowledged'] ?? 0,
            'activeBrain' => $status['channels']['active_provider'] ?? 'Unknown',
            'overallStatus' => $server['overall_status'] ?? 'unknown',
            'services' => $services,
            'activeServices' => $activeServices,
            'totalServices' => $totalServices,
        ];
    }

    public function getWidgets(): array
    {
        return [
            \App\Filament\Widgets\ControlCenterWidget::class,
            \App\Filament\Widgets\ServicesStatusWidget::class,
            \App\Filament\Widgets\AlertsOverviewWidget::class,
            \App\Filament\Widgets\IntelligencePreviewWidget::class,
            \App\Filament\Widgets\SystemActivityWidget::class,
            \App\Filament\Widgets\TerminalWidget::class,
        ];
    }
}
