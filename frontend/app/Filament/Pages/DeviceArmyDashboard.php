<?php

namespace App\Filament\Pages;

use Filament\Actions\Action;
use Filament\Pages\Page;
use Illuminate\Support\Facades\Http;

class DeviceArmyDashboard extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-cpu-chip';

    protected static ?string $navigationGroup = 'Device Army';

    protected static ?int $navigationSort = 1;

    protected static string $view = 'filament.pages.device-army-dashboard';

    protected static ?string $title = 'Device Army Command Center';

    public array $devices = [];

    public array $stats = [];

    public bool $loading = true;

    public function mount(): void
    {
        $this->refresh();
    }

    public function refresh(): void
    {
        $this->loading = true;

        try {
            $baseUrl = rtrim(config('services.sanaa_engine.url', 'http://127.0.0.1:8100'), '/');
            $apiKey = config('services.sanaa_engine.key', '');

            // Fetch devices from Python backend
            $response = Http::withToken($apiKey)
                ->timeout(10)
                ->get("{$baseUrl}/device-army/devices");

            if ($response->successful()) {
                $data = $response->json();
                $this->devices = $data['devices'] ?? [];
                $this->stats = [
                    'total' => $data['total'] ?? count($this->devices),
                    'online' => count(array_filter($this->devices, fn ($d) => in_array($d['status'] ?? '', ['online', 'idle', 'busy']))),
                    'offline' => count(array_filter($this->devices, fn ($d) => ($d['status'] ?? '') === 'offline')),
                ];
            }

            // Fetch stats
            $statsResponse = Http::withToken($apiKey)
                ->timeout(10)
                ->get("{$baseUrl}/device-army/stats");

            if ($statsResponse->successful()) {
                $this->stats = array_merge($this->stats, $statsResponse->json() ?? []);
            }
        } catch (\Exception $e) {
            $this->stats = ['total' => 0, 'online' => 0, 'offline' => 0, 'error' => $e->getMessage()];
        }

        $this->loading = false;
    }

    public function getDeviceStatusColor(string $status): string
    {
        return match ($status) {
            'online' => 'success',
            'idle' => 'warning',
            'busy' => 'info',
            'offline' => 'gray',
            'error' => 'danger',
            default => 'gray',
        };
    }

    public function getDeviceStatusIcon(string $status): string
    {
        return match ($status) {
            'online' => 'heroicon-m-check-circle',
            'idle' => 'heroicon-m-clock',
            'busy' => 'heroicon-m-play-circle',
            'offline' => 'heroicon-m-x-circle',
            'error' => 'heroicon-m-exclamation-triangle',
            default => 'heroicon-m-question-mark-circle',
        };
    }

    public function getRoleIcon(string $role): string
    {
        return match ($role) {
            'scout' => 'heroicon-m-eye',
            'tester' => 'heroicon-m-beaker',
            'media' => 'heroicon-m-camera',
            'analyst' => 'heroicon-m-chart-bar',
            'observer' => 'heroicon-m-magnifying-glass',
            default => 'heroicon-m-user-circle',
        };
    }

    protected function getHeaderActions(): array
    {
        return [
            Action::make('refresh')
                ->label('Refresh Fleet')
                ->icon('heroicon-m-arrow-path')
                ->action(fn () => $this->refresh()),

            Action::make('register_device')
                ->label('Register Device')
                ->icon('heroicon-m-plus-circle')
                ->color('success')
                ->url(fn () => url('/admin/device-army/register-device')),
        ];
    }
}
