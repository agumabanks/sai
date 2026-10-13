<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class MailcowCommand extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-envelope-open';

    protected static ?string $navigationGroup = 'Infrastructure';

    protected static ?int $navigationSort = 13;

    protected static string $view = 'filament.pages.mailcow-command';

    protected static ?string $title = 'Mailcow Command';

    protected static ?string $navigationLabel = 'Mailcow Agent';

    public string $detailOutput = '';

    public string $activeTab = 'container_health';

    public bool $isLoading = false;

    public function mount(): void
    {
        $this->runCheck('container_health');
    }

    public function runCheck(string $action): void
    {
        $this->isLoading = true;
        $this->activeTab = $action;

        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('mailcow_agent', ['action' => $action], 'admin:mailcow_command');

        $this->detailOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));
        $this->isLoading = false;

        $success = $result['success'] ?? false;
        if ($success) {
            Notification::make()->title(ucfirst(str_replace('_', ' ', $action)).' status OK')->success()->send();
        } else {
            Notification::make()->title(ucfirst(str_replace('_', ' ', $action)).' check failed or issues found')->warning()->send();
        }
    }

    public function refreshAll(): void
    {
        $this->runCheck($this->activeTab);
    }
}
