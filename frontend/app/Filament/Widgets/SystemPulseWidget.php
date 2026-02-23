<?php

namespace App\Filament\Widgets;

use App\Services\SanaaEngineService;
use Filament\Widgets\Widget;

class SystemPulseWidget extends Widget
{
    protected static string $view = 'filament.widgets.system-pulse-widget';
    
    protected static ?string $pollingInterval = '5s';
    
    protected static bool $isLazy = false;

    // To ensure it appears before or after other widgets as needed
    protected static ?int $sort = -5;

    public array $data = [];

    public function mount()
    {
        $this->refreshData();
    }

    public function refreshData()
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();

        if (isset($status['status']) && $status['status'] === 'offline') {
            $this->data = [
                'online' => false,
                'error' => 'Backend Disconnected',
            ];
            return;
        }

        $this->data = [
            'online' => true,
            'cpu' => $status['server']['cpu']['percent'] ?? 0,
            'ram' => $status['server']['memory']['percent'] ?? 0,
            'disk' => $status['server']['disk']['percent'] ?? 0,
            'brain_provider' => $status['brain']['active_provider'] ?? 'unknown',
            'healer_active' => !empty($status['healer']['active_failures']),
            'failures' => $status['healer']['active_failures'] ?? [],
            'thresholds' => $status['healer']['tier_thresholds'] ?? [],
        ];
    }

    public function getProviderIcon(): string
    {
        return match($this->data['brain_provider'] ?? 'local') {
            'local' => 'heroicon-m-cpu-chip',
            'groq' => 'heroicon-m-bolt',
            'openrouter' => 'heroicon-m-globe-alt',
            default => 'heroicon-m-question-mark-circle',
        };
    }

    public function getProviderColor(): string
    {
        return match($this->data['brain_provider'] ?? 'local') {
            'local' => 'emerald',
            'groq' => 'amber',
            'openrouter' => 'indigo',
            default => 'gray',
        };
    }
}
