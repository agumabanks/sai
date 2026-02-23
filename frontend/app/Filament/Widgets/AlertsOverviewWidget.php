<?php

namespace App\Filament\Widgets;

use App\Services\SanaaEngineService;
use Filament\Widgets\Widget;

class AlertsOverviewWidget extends Widget
{
    protected static string $view = 'filament.widgets.alerts-overview-widget';

    protected static ?string $pollingInterval = '15s';

    protected static bool $isLazy = false;

    public array $alerts = [];
    public int $totalCount = 0;
    public array $severityCounts = [];

    public function mount()
    {
        $this->refreshAlerts();
    }

    public function refreshAlerts()
    {
        $engine = app(SanaaEngineService::class);

        // Get status for counts
        $status = $engine->getStatus();
        $this->totalCount = $status['alerts']['unacknowledged'] ?? 0;

        // Get recent alerts for list
        $raw = $engine->getAlerts(8);

        $this->severityCounts = ['critical' => 0, 'high' => 0, 'warning' => 0, 'info' => 0];

        $this->alerts = collect($raw)->map(function ($item) {
            $severity = $item['severity'] ?? 'info';
            if (isset($this->severityCounts[$severity])) {
                $this->severityCounts[$severity]++;
            }
            $time = $item['created_at'] ?? '';
            return [
                'id' => $item['id'] ?? 0,
                'severity' => $severity,
                'message' => $item['message'] ?? 'Unknown alert',
                'metric' => $item['metric'] ?? '',
                'time' => $time ? \Carbon\Carbon::parse($time) : now(),
            ];
        })->toArray();
    }
}
