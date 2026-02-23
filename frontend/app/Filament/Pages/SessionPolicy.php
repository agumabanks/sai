<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Forms\Components\Section;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Concerns\InteractsWithForms;
use Filament\Forms\Contracts\HasForms;
use Filament\Forms\Form;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class SessionPolicy extends Page implements HasForms
{
    use InteractsWithForms;

    protected static ?string $navigationIcon = 'heroicon-o-chat-bubble-left-right';
    protected static ?string $navigationGroup = 'Operations';
    protected static ?int $navigationSort = 3;
    protected static string $view = 'filament.pages.session-policy';

    public ?array $data = [];
    public array $sessions = [];
    public ?array $selectedSession = null;

    public function mount(): void
    {
        $this->refreshData();
    }

    public function refreshData(): void
    {
        $engine = app(SanaaEngineService::class);
        $policyPayload = $engine->getSessionPolicy();
        $policy = $policyPayload['policy'] ?? [];
        $sessionsPayload = $engine->getSessions(50);
        $this->sessions = $sessionsPayload['sessions'] ?? [];

        $this->form->fill([
            'dm_scope' => $policy['dm_scope'] ?? 'per-channel-peer',
            'reset_mode' => $policy['reset']['mode'] ?? 'daily_or_idle',
            'reset_at_hour' => (string)($policy['reset']['at_hour'] ?? 4),
            'reset_idle_minutes' => (string)($policy['reset']['idle_minutes'] ?? 240),
            'send_default' => $policy['send_policy']['default'] ?? 'allow',
            'send_rules_json' => json_encode($policy['send_policy']['rules'] ?? [], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES),
            'reset_triggers' => implode(',', $policy['reset_triggers'] ?? ['/new', '/reset']),
        ]);
    }

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Section::make('Session Policy')
                    ->description('OpenClaw-inspired session isolation, resets, and send policy for Sanaa channels.')
                    ->schema([
                        Select::make('dm_scope')
                            ->label('DM Scope')
                            ->options([
                                'main' => 'Main (shared DM context - less safe)',
                                'per-peer' => 'Per Peer',
                                'per-channel-peer' => 'Per Channel + Peer (Recommended)',
                            ])
                            ->required(),
                        Select::make('reset_mode')
                            ->label('Reset Mode')
                            ->options([
                                'none' => 'None',
                                'daily' => 'Daily',
                                'idle' => 'Idle',
                                'daily_or_idle' => 'Daily or Idle (Recommended)',
                            ])
                            ->required(),
                        TextInput::make('reset_at_hour')
                            ->label('Daily Reset Hour')
                            ->numeric()
                            ->required(),
                        TextInput::make('reset_idle_minutes')
                            ->label('Idle Reset Minutes')
                            ->numeric()
                            ->required(),
                        Select::make('send_default')
                            ->label('Send Policy Default')
                            ->options([
                                'allow' => 'Allow',
                                'deny' => 'Deny',
                            ])
                            ->required(),
                        Textarea::make('send_rules_json')
                            ->label('Send Rules (JSON)')
                            ->rows(6)
                            ->helperText('Array of rules: [{"action":"deny","match":{"channel":"web","chatType":"group"}}]'),
                        TextInput::make('reset_triggers')
                            ->label('Reset Triggers')
                            ->helperText('Comma-separated slash commands, e.g. /new,/reset'),
                    ]),
            ])
            ->statePath('data');
    }

    public function submit(): void
    {
        $engine = app(SanaaEngineService::class);
        $state = $this->form->getState();
        $rules = json_decode((string)($state['send_rules_json'] ?? '[]'), true);
        $payload = [
            'dm_scope' => (string)($state['dm_scope'] ?? 'per-channel-peer'),
            'reset' => [
                'mode' => (string)($state['reset_mode'] ?? 'daily_or_idle'),
                'at_hour' => (int)($state['reset_at_hour'] ?? 4),
                'idle_minutes' => (int)($state['reset_idle_minutes'] ?? 240),
            ],
            'send_policy' => [
                'default' => (string)($state['send_default'] ?? 'allow'),
                'rules' => is_array($rules) ? $rules : [],
            ],
            'reset_triggers' => array_values(array_filter(array_map('trim', explode(',', (string)($state['reset_triggers'] ?? '/new,/reset'))))),
        ];
        $res = $engine->updateSessionPolicy($payload);
        if (($res['status'] ?? null) === 'success') {
            Notification::make()->title('Session policy updated')->success()->send();
            $this->refreshData();
            return;
        }
        Notification::make()->title('Failed to update session policy')->body((string)($res['error'] ?? 'Unknown error'))->danger()->send();
    }

    public function inspectSession(string $sessionId): void
    {
        $engine = app(SanaaEngineService::class);
        $this->selectedSession = $engine->getSessionDetail($sessionId);
    }

    public function resetSessionAction(string $sessionId): void
    {
        $engine = app(SanaaEngineService::class);
        $res = $engine->resetSession($sessionId);
        if (($res['status'] ?? null) === 'success') {
            Notification::make()->title('Session reset')->success()->send();
            $this->refreshData();
            return;
        }
        Notification::make()->title('Session reset failed')->body((string)($res['error'] ?? 'Unknown error'))->danger()->send();
    }

    public function setSendOverride(string $sessionId, string $mode): void
    {
        $engine = app(SanaaEngineService::class);
        $res = $engine->setSessionSendPolicy($sessionId, $mode);
        if (($res['status'] ?? null) === 'success') {
            Notification::make()->title("Send policy override: {$mode}")->success()->send();
            $this->refreshData();
            return;
        }
        Notification::make()->title('Send policy override failed')->body((string)($res['error'] ?? 'Unknown error'))->danger()->send();
    }
}

