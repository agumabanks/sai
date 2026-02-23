<?php

namespace App\Livewire;

use App\Services\SanaaEngineService;
use Livewire\Component;
use Filament\Notifications\Notification;

class SanaaFab extends Component
{
    public bool $isOpen = false;
    public array $status = [];
    public bool $securityScanner = true;
    public bool $autoHealer = true;
    public ?array $latestSignal = null;

    // Sub-modal state
    public ?string $activeModal = null;
    public array $modalData = [];

    protected $listeners = ['command-sent' => '$refresh'];

    public function mount()
    {
        $this->refreshStatus();
    }

    public function refreshStatus()
    {
        $engine = app(SanaaEngineService::class);
        $this->status = $engine->getStatus();
        $this->latestSignal = $engine->getLatestSignal();
    }

    public function toggleMenu()
    {
        $this->isOpen = !$this->isOpen;
        if ($this->isOpen) {
            $this->refreshStatus();
            $this->activeModal = null;
            $this->modalData = [];
        }
    }

    public function openModal(string $modal)
    {
        $this->activeModal = $modal;
        $this->modalData = $this->fetchModalData($modal);
    }

    public function closeModal()
    {
        $this->activeModal = null;
        $this->modalData = [];
    }

    private function fetchModalData(string $modal): array
    {
        $engine = app(SanaaEngineService::class);

        return match ($modal) {
            'brain' => [
                'provider' => $this->status['channels']['active_provider'] ?? 'LOCAL',
                'providers' => ['LOCAL', 'GROQ', 'OPENROUTER'],
                'model' => $this->status['channels']['active_model'] ?? 'Unknown',
                'uptime' => $this->status['system']['uptime'] ?? 'N/A',
            ],
            'skills' => [
                'items' => [
                    ['name' => 'Server Health', 'status' => 'active', 'desc' => 'System monitoring & alerts'],
                    ['name' => 'App Monitor', 'status' => 'active', 'desc' => 'Application lifecycle watch'],
                    ['name' => 'Web Test', 'status' => 'active', 'desc' => 'HTTP endpoint validation'],
                    ['name' => 'Security Scan', 'status' => 'active', 'desc' => 'Vulnerability detection'],
                ],
            ],
            'flows' => [
                'items' => [
                    ['name' => 'Daily Triage', 'steps' => 5, 'status' => 'ready'],
                    ['name' => 'Deploy App', 'steps' => 4, 'status' => 'ready'],
                    ['name' => 'Incident Response', 'steps' => 6, 'status' => 'ready'],
                ],
            ],
            'stats' => [
                'today' => $this->status['usage']['today'] ?? '0 requests',
                'cost' => $this->status['usage']['cost'] ?? '$0.00',
                'model' => $this->status['channels']['active_model'] ?? 'Unknown',
                'provider' => $this->status['channels']['active_provider'] ?? 'LOCAL',
            ],
            default => [],
        };
    }

    public function triggerAction(string $command, string $label)
    {
        $engine = app(SanaaEngineService::class);
        $engine->executeCommand($command);

        Notification::make()
            ->title($label . " Initiated")
            ->body("Action sent to Sanaa Intelligence backend.")
            ->info()
            ->send();

        $this->isOpen = false;
        $this->activeModal = null;
    }

    public function togglePreference(string $key)
    {
        $this->$key = !$this->$key;
        $engine = app(SanaaEngineService::class);
        $engine->updatePreference($key, $this->$key);

        Notification::make()
            ->title("Preference Updated")
            ->body(str($key)->headline() . " is now " . ($this->$key ? "ENABLED" : "DISABLED"))
            ->success()
            ->send();
    }

    public function render()
    {
        return view('livewire.sanaa-fab');
    }
}
