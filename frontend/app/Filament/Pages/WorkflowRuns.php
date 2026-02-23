<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class WorkflowRuns extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-arrow-path';
    protected static ?string $navigationGroup = 'Operations';
    protected static ?int $navigationSort = 2;
    protected static string $view = 'filament.pages.workflow-runs';

    public array $workflows = [];
    public array $runs = [];
    public ?array $selectedRun = null;
    public ?array $selectedApproval = null;

    public function mount(): void
    {
        $this->refreshData();
    }

    public function refreshData(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->workflows = $engine->getWorkflows()['workflows'] ?? [];
        $this->runs = $engine->getWorkflowRuns(50)['runs'] ?? [];
    }

    public function viewRun(int $runId): void
    {
        $engine = app(SanaaEngineService::class);
        $this->selectedRun = $engine->getWorkflowRun($runId);
        $this->selectedApproval = $engine->getWorkflowApproval($runId);
    }

    public function startWorkflow(string $name): void
    {
        $engine = app(SanaaEngineService::class);
        $res = $engine->runWorkflow($name, []);
        if (!empty($res['error'])) {
            Notification::make()->title('Failed to start workflow')->body((string) $res['error'])->danger()->send();
            return;
        }
        Notification::make()->title("Workflow started: {$name}")->success()->send();
        $this->refreshData();
    }

    public function approveRun(int $runId): void
    {
        $engine = app(SanaaEngineService::class);
        $approval = $engine->getWorkflowApproval($runId);
        $token = (string) ($approval['resume_token'] ?? '');
        if ($token === '') {
            Notification::make()->title('No resume token found')->danger()->send();
            return;
        }
        $res = $engine->resumeWorkflowRun($runId, true, $token);
        if (($res['status'] ?? null) !== 'success') {
            Notification::make()->title('Resume failed')->body((string) ($res['error'] ?? 'Unknown error'))->danger()->send();
            return;
        }
        Notification::make()->title("Workflow resumed: #{$runId}")->success()->send();
        $this->viewRun($runId);
        $this->refreshData();
    }

    public function denyRun(int $runId): void
    {
        $engine = app(SanaaEngineService::class);
        $approval = $engine->getWorkflowApproval($runId);
        $token = (string) ($approval['resume_token'] ?? '');
        if ($token === '') {
            Notification::make()->title('No resume token found')->danger()->send();
            return;
        }
        $res = $engine->resumeWorkflowRun($runId, false, $token);
        if (($res['status'] ?? null) !== 'success') {
            Notification::make()->title('Decision failed')->body((string) ($res['error'] ?? 'Unknown error'))->danger()->send();
            return;
        }
        Notification::make()->title("Workflow denied/cancelled: #{$runId}")->warning()->send();
        $this->viewRun($runId);
        $this->refreshData();
    }

    public function cancelRun(int $runId): void
    {
        $engine = app(SanaaEngineService::class);
        $res = $engine->cancelWorkflowRun($runId);
        if (($res['status'] ?? null) !== 'success') {
            Notification::make()->title('Cancel failed')->body((string) ($res['error'] ?? 'Unknown error'))->danger()->send();
            return;
        }
        Notification::make()->title("Workflow cancelled: #{$runId}")->warning()->send();
        $this->viewRun($runId);
        $this->refreshData();
    }
}

