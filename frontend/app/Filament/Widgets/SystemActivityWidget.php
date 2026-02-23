<?php

namespace App\Filament\Widgets;

use App\Services\SanaaEngineService;
use Filament\Widgets\Widget;

class SystemActivityWidget extends Widget
{
    protected static string $view = 'filament.widgets.system-activity-widget';
    
    protected static ?string $pollingInterval = '10s';
    
    protected static bool $isLazy = false;

    public array $activities = [];

    public function mount()
    {
        $this->refreshActivities();
    }

    public function refreshActivities()
    {
        $engine = app(SanaaEngineService::class);

        $raw = $engine->getActivities(20);

        if (empty($raw)) {
            // Fallback when backend is unreachable
            $this->activities = [[
                'type' => 'info',
                'title' => 'Waiting for Data',
                'description' => 'No recent activity — system is idle or backend is warming up',
                'time' => now(),
                'status' => 'info',
                'icon' => 'heroicon-m-clock',
            ]];
            return;
        }

        $this->activities = collect($raw)->map(function ($item) {
            $time = $item['time'] ?? '';
            return [
                'type' => $item['type'] ?? 'system',
                'title' => $item['title'] ?? 'System Event',
                'description' => $item['description'] ?? '',
                'time' => $time ? \Carbon\Carbon::parse($time) : now(),
                'status' => $item['status'] ?? 'info',
                'icon' => $item['icon'] ?? 'heroicon-m-information-circle',
            ];
        })->toArray();
    }

    public function getStatusColor(string $status): string
    {
        return match($status) {
            'success' => 'emerald',
            'warning' => 'amber',
            'error' => 'red',
            'info' => 'indigo',
            default => 'gray',
        };
    }
}
