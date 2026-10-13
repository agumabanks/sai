<?php

namespace App\Filament\Pages;

use Filament\Actions\Action;
use Filament\Forms\Concerns\InteractsWithForms;
use Filament\Pages\Page;
use Illuminate\Support\Facades\Http;

class DeviceTaskManager extends Page
{
    use InteractsWithForms;

    protected static ?string $navigationIcon = 'heroicon-o-list-bullet';

    protected static ?string $navigationGroup = 'Device Army';

    protected static ?int $navigationSort = 3;

    protected static string $view = 'filament.pages.device-task-manager';

    protected static ?string $title = 'Task Manager';

    public array $devices = [];

    public string $selectedDeviceId = '';

    public string $taskType = '';

    public string $taskPayload = '';

    public int $taskPriority = 0;

    public ?string $lastResult = null;

    public bool $showForm = false;

    public function mount(): void
    {
        $this->loadDevices();
    }

    public function loadDevices(): void
    {
        try {
            $baseUrl = rtrim(config('services.sanaa_engine.url', 'http://127.0.0.1:8100'), '/');
            $apiKey = config('services.sanaa_engine.key', '');

            $response = Http::withToken($apiKey)
                ->timeout(10)
                ->get("{$baseUrl}/device-army/devices");

            if ($response->successful()) {
                $data = $response->json();
                $this->devices = $data['devices'] ?? [];
            }
        } catch (\Exception $e) {
            $this->devices = [];
        }
    }

    public function createTask(): void
    {
        if (empty($this->selectedDeviceId) || empty($this->taskType)) {
            return;
        }

        try {
            $baseUrl = rtrim(config('services.sanaa_engine.url', 'http://127.0.0.1:8100'), '/');
            $apiKey = config('services.sanaa_engine.key', '');

            $payload = ! empty($this->taskPayload)
                ? json_decode($this->taskPayload, true) ?? []
                : [];

            $response = Http::withToken($apiKey)
                ->timeout(10)
                ->post("{$baseUrl}/device-army/tasks", [
                    'device_id' => $this->selectedDeviceId,
                    'task_type' => $this->taskType,
                    'payload' => $payload,
                    'priority' => $this->taskPriority,
                ]);

            if ($response->successful()) {
                $taskData = $response->json();
                $this->lastResult = "Task created: {$taskData['task_id']} ({$taskData['task_type']})";
                $this->showForm = false;
                $this->taskType = '';
                $this->taskPayload = '';
                $this->taskPriority = 0;
            } else {
                $this->lastResult = 'Error: '.$response->body();
            }
        } catch (\Exception $e) {
            $this->lastResult = 'Error: '.$e->getMessage();
        }
    }

    protected function getHeaderActions(): array
    {
        return [
            Action::make('new_task')
                ->label('New Task')
                ->icon('heroicon-m-plus-circle')
                ->color('success')
                ->action(fn () => $this->showForm = true),
        ];
    }
}
