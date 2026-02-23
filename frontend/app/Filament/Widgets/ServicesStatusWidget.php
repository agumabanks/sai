<?php

namespace App\Filament\Widgets;

use App\Services\SanaaEngineService;
use Filament\Widgets\Widget;

class ServicesStatusWidget extends Widget
{
    protected static string $view = 'filament.widgets.services-status-widget';

    protected static ?string $pollingInterval = '10s';

    protected static bool $isLazy = false;

    public array $services = [];
    public int $activeCount = 0;
    public int $totalCount = 0;

    public function mount()
    {
        $this->refreshServices();
    }

    public function refreshServices()
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();

        $raw = $status['server']['services'] ?? [];

        $this->services = [];
        foreach ($raw as $name => $state) {
            $this->services[] = [
                'name' => $name,
                'label' => $this->formatServiceName($name),
                'active' => $state === 'active',
                'state' => $state,
            ];
        }

        $this->activeCount = count(array_filter($this->services, fn($s) => $s['active']));
        $this->totalCount = count($this->services);
    }

    protected function formatServiceName(string $name): string
    {
        return match($name) {
            'nginx' => 'Nginx',
            'php8.4-fpm' => 'PHP-FPM',
            'redis-server' => 'Redis',
            'postgresql' => 'PostgreSQL',
            'supervisor' => 'Supervisor',
            default => ucfirst(str_replace(['-', '_'], ' ', $name)),
        };
    }

    public function getServiceIcon(string $name): string
    {
        return match($name) {
            'nginx' => 'heroicon-m-globe-alt',
            'php8.4-fpm' => 'heroicon-m-code-bracket',
            'redis-server' => 'heroicon-m-bolt',
            'postgresql' => 'heroicon-m-circle-stack',
            'supervisor' => 'heroicon-m-cog-6-tooth',
            default => 'heroicon-m-server-stack',
        };
    }
}
