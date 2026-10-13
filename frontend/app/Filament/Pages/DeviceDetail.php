<?php

namespace App\Filament\Pages;

use Filament\Actions\Action;
use Filament\Pages\Page;
use Illuminate\Support\Facades\Http;

class DeviceDetail extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-device-phone-mobile';

    protected static ?string $navigationGroup = 'Device Army';

    protected static ?int $navigationSort = 2;

    protected static string $view = 'filament.pages.device-detail';

    protected static ?string $title = 'Device Detail';

    protected static ?string $slug = 'device-army/devices/{deviceId}';

    public ?string $deviceId = null;

    public array $deviceData = [];

    public array $recentLogs = [];

    public array $recentTasks = [];

    public bool $loading = true;

    public string $commandType = '';

    public string $commandPayload = '';

    public function mount(string $deviceId): void
    {
        $this->deviceId = $deviceId;
        $this->refresh();
    }

    public function refresh(): void
    {
        $this->loading = true;

        try {
            $baseUrl = rtrim(config('services.sanaa_engine.url', 'http://127.0.0.1:8100'), '/');
            $apiKey = config('services.sanaa_engine.key', '');

            $response = Http::withToken($apiKey)
                ->timeout(10)
                ->get("{$baseUrl}/device-army/devices/{$this->deviceId}");

            if ($response->successful()) {
                $data = $response->json();
                $this->deviceData = $data['device'] ?? [];
                $this->recentLogs = $data['recent_logs'] ?? [];
                $this->recentTasks = $data['recent_tasks'] ?? [];
            }
        } catch (\Exception $e) {
            $this->deviceData = ['error' => $e->getMessage()];
        }

        $this->loading = false;
    }

    public function sendCommand(): void
    {
        if (empty($this->commandType)) {
            return;
        }

        try {
            $baseUrl = rtrim(config('services.sanaa_engine.url', 'http://127.0.0.1:8100'), '/');
            $apiKey = config('services.sanaa_engine.key', '');

            $payload = ! empty($this->commandPayload)
                ? json_decode($this->commandPayload, true) ?? []
                : [];

            $response = Http::withToken($apiKey)
                ->timeout(10)
                ->post("{$baseUrl}/device-army/command", [
                    'device_id' => $this->deviceId,
                    'command_type' => $this->commandType,
                    'payload' => $payload,
                ]);

            if ($response->successful()) {
                $this->commandType = '';
                $this->commandPayload = '';
                $this->refresh();
            }
        } catch (\Exception $e) {
            // Handle error
        }
    }

    public function getStatusColor(string $status): string
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

    public function getLogSeverityColor(string $severity): string
    {
        return match ($severity) {
            'critical' => 'danger',
            'high' => 'warning',
            'medium' => 'info',
            'low' => 'gray',
            default => 'gray',
        };
    }

    public function getTaskStatusColor(string $status): string
    {
        return match ($status) {
            'completed' => 'success',
            'failed' => 'danger',
            'in_progress' => 'info',
            'pending' => 'warning',
            default => 'gray',
        };
    }

    protected function getHeaderActions(): array
    {
        return [
            Action::make('back')
                ->label('Back to Fleet')
                ->icon('heroicon-m-arrow-left')
                ->url(fn () => url('/admin/device-army-dashboard')),

            Action::make('refresh')
                ->label('Refresh')
                ->icon('heroicon-m-arrow-path')
                ->action(fn () => $this->refresh()),
        ];
    }
}
