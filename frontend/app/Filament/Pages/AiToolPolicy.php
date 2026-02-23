<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Forms\Components\Section;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Contracts\HasForms;
use Filament\Forms\Concerns\InteractsWithForms;
use Filament\Forms\Form;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class AiToolPolicy extends Page implements HasForms
{
    use InteractsWithForms;

    protected static ?string $navigationIcon = 'heroicon-o-shield-check';
    protected static ?string $navigationGroup = 'Intelligence';
    protected static ?int $navigationSort = 2;
    protected static string $view = 'filament.pages.ai-tool-policy';

    public ?array $data = [];
    public array $skills = [];

    public function mount(): void
    {
        $this->reload();
    }

    public function refreshData(): void
    {
        $this->reload();
    }

    protected function reload(): void
    {
        $engine = app(SanaaEngineService::class);
        $payload = $engine->getToolPolicy();
        $skillsPayload = $engine->getSkills();

        $policy = $payload['policy'] ?? ($skillsPayload['tool_policy'] ?? []);
        $this->skills = $skillsPayload['skills'] ?? [];

        $this->form->fill([
            'enabled' => (bool)($policy['enabled'] ?? true),
            'mode' => (string)($policy['mode'] ?? 'allowlist'),
            'allow' => implode(',', $policy['allow'] ?? []),
            'deny' => implode(',', $policy['deny'] ?? []),
            'groups_allow' => implode(',', $policy['groups']['allow'] ?? []),
            'groups_deny' => implode(',', $policy['groups']['deny'] ?? []),
            'by_provider_json' => json_encode($policy['by_provider'] ?? new \stdClass(), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES),
            'by_channel_json' => json_encode($policy['by_channel'] ?? new \stdClass(), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES),
        ]);
    }

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Section::make('Tool Policy')
                    ->description('Control which skills the Sanaa brain may auto-call.')
                    ->schema([
                        Select::make('enabled')
                            ->label('Policy Enabled')
                            ->options([1 => 'Enabled', 0 => 'Disabled'])
                            ->required(),
                        Select::make('mode')
                            ->label('Policy Mode')
                            ->options([
                                'allowlist' => 'Allowlist (Recommended)',
                                'allow_all' => 'Allow All (Less safe)',
                            ])
                            ->required(),
                        TextInput::make('allow')
                            ->label('Allow Skills')
                            ->helperText('Comma-separated skill names.'),
                        TextInput::make('deny')
                            ->label('Deny Skills')
                            ->helperText('Comma-separated skill names.'),
                        TextInput::make('groups_allow')
                            ->label('Allow Groups')
                            ->helperText('Comma-separated tags/groups (e.g. monitoring,diagnostics).'),
                        TextInput::make('groups_deny')
                            ->label('Deny Groups')
                            ->helperText('Comma-separated tags/groups.'),
                        \Filament\Forms\Components\Textarea::make('by_provider_json')
                            ->label('Provider Rules (JSON)')
                            ->rows(6),
                        \Filament\Forms\Components\Textarea::make('by_channel_json')
                            ->label('Channel Rules (JSON)')
                            ->rows(6),
                    ]),
            ])
            ->statePath('data');
    }

    public function submit(): void
    {
        $state = $this->form->getState();
        $engine = app(SanaaEngineService::class);

        $byProvider = json_decode((string)($state['by_provider_json'] ?? '{}'), true);
        $byChannel = json_decode((string)($state['by_channel_json'] ?? '{}'), true);

        $payload = [
            'enabled' => (bool)($state['enabled'] ?? true),
            'mode' => (string)($state['mode'] ?? 'allowlist'),
            'allow' => $this->csvToArray($state['allow'] ?? ''),
            'deny' => $this->csvToArray($state['deny'] ?? ''),
            'groups' => [
                'allow' => $this->csvToArray($state['groups_allow'] ?? ''),
                'deny' => $this->csvToArray($state['groups_deny'] ?? ''),
            ],
            'by_provider' => is_array($byProvider) ? $byProvider : [],
            'by_channel' => is_array($byChannel) ? $byChannel : [],
        ];

        $res = $engine->updateToolPolicy($payload);
        if (($res['status'] ?? null) === 'success') {
            Notification::make()->title('Tool policy updated')->success()->send();
            $this->reload();
            return;
        }
        Notification::make()->title('Failed to update tool policy')->body((string)($res['error'] ?? 'Unknown error'))->danger()->send();
    }

    public function toggleSkill(string $skill, bool $enabled): void
    {
        $engine = app(SanaaEngineService::class);
        $res = $engine->setSkillEnabled($skill, $enabled);
        if (!empty($res['error'])) {
            Notification::make()->title('Skill toggle failed')->body((string)$res['error'])->danger()->send();
            return;
        }
        Notification::make()->title("Skill {$skill} " . ($enabled ? 'enabled' : 'disabled'))->success()->send();
        $this->reload();
    }

    public function changeExposure(string $skill, string $exposure): void
    {
        $engine = app(SanaaEngineService::class);
        $res = $engine->setSkillExposure($skill, $exposure);
        if (!empty($res['error'])) {
            Notification::make()->title('Exposure update failed')->body((string)$res['error'])->danger()->send();
            return;
        }
        Notification::make()->title("Exposure updated: {$skill}")->success()->send();
        $this->reload();
    }

    protected function csvToArray(string $value): array
    {
        return array_values(array_filter(array_map('trim', explode(',', $value))));
    }
}
