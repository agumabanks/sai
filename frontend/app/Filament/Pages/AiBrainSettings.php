<?php

namespace App\Filament\Pages;

use Filament\Pages\Page;
use Filament\Forms\Contracts\HasForms;
use Filament\Forms\Concerns\InteractsWithForms;
use Filament\Forms\Form;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Section;
use Filament\Notifications\Notification;
use App\Services\SanaaEngineService;

class AiBrainSettings extends Page implements HasForms
{
    use InteractsWithForms;

    protected static ?string $navigationIcon = 'heroicon-o-cpu-chip';
    protected static ?string $navigationGroup = 'Intelligence';
    protected static ?int $navigationSort = 1;
    protected static string $view = 'filament.pages.ai-brain-settings';

    public ?array $data = [];

    public function mount(): void
    {
        $defaults = [
            'provider' => 'auto',
            'claude_source' => 'anthropic',
            'auto_provider_order' => 'groq,anthropic,openrouter,local',
            'models' => [
                'local' => 'qwen2.5:7b',
                'groq' => 'llama-3.3-70b-versatile',
                'anthropic_fast' => 'claude-3-haiku-20240307',
                'anthropic_premium' => 'claude-3-5-sonnet-20240620',
                'openrouter' => 'liquid/lfm-40b',
            ],
            'keys' => [
                'anthropic' => '',
                'groq' => '',
                'openrouter' => '',
            ],
        ];

        $engine = app(SanaaEngineService::class);
        $config = $engine->getBrainConfig();

        if (!empty($config)) {
            $defaults['provider'] = $config['provider'] ?? $defaults['provider'];
            $defaults['claude_source'] = $config['claude_source'] ?? $defaults['claude_source'];
            $defaults['auto_provider_order'] = $config['auto_provider_order'] ?? $defaults['auto_provider_order'];
            $defaults['models'] = array_merge($defaults['models'], $config['models'] ?? []);
        }

        $this->form->fill($defaults);
    }

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Section::make('Core Intelligence settings')
                    ->description('Manage how the Sanaa AI Brain processes incoming commands and handles autonomy.')
                    ->schema([
                        Select::make('provider')
                            ->label('Active LLM Provider')
                            ->options([
                                'auto' => 'Auto Engine (Recommended)',
                                'claude' => 'Claude Mode (Switchable Source)',
                                'local' => 'Local Compute / Ollama (Secure)',
                                'groq' => 'Groq Cloud Compute (Ultra-fast)',
                                'openrouter' => 'OpenRouter Cloud Compute (Versatile)',
                            ])
                            ->required(),
                        Select::make('claude_source')
                            ->label('Claude Mode Source')
                            ->options([
                                'anthropic' => 'Real Claude (Anthropic)',
                                'groq' => 'Groq (Claude-compatible fallback mode)',
                                'openrouter' => 'OpenRouter (Cheap/Fallback mode)',
                            ])
                            ->helperText('When provider is set to Claude mode, choose which backend powers it.')
                            ->required(),
                        TextInput::make('auto_provider_order')
                            ->label('Auto Provider Fallback Order')
                            ->helperText('Comma-separated order for auto mode. Allowed: groq, anthropic, openrouter, local, openai')
                            ->placeholder('groq,anthropic,openrouter,local'),
                    ]),
                Section::make('Provider API Keys')
                    ->description('Leave any key blank to keep the currently stored value.')
                    ->schema([
                        TextInput::make('keys.anthropic')
                            ->label('Anthropic (Claude) API Key')
                            ->password()
                            ->helperText('Used when Claude mode source is Anthropic.'),
                        TextInput::make('keys.groq')
                            ->label('Groq API Key')
                            ->password()
                            ->helperText('Used for Groq provider and Claude mode when source = Groq.'),
                        TextInput::make('keys.openrouter')
                            ->label('OpenRouter API Key')
                            ->password()
                            ->helperText('Used for OpenRouter provider and Claude mode when source = OpenRouter.'),
                    ]),
                Section::make('Model IDs')
                    ->description('Editable LiteLLM model identifiers for each source.')
                    ->schema([
                        TextInput::make('models.local')
                            ->label('Local Ollama Model')
                            ->required(),
                        TextInput::make('models.groq')
                            ->label('Groq Model')
                            ->required(),
                        TextInput::make('models.anthropic_fast')
                            ->label('Anthropic Fast Model')
                            ->required(),
                        TextInput::make('models.anthropic_premium')
                            ->label('Anthropic Premium Model')
                            ->required(),
                        TextInput::make('models.openrouter')
                            ->label('OpenRouter Model')
                            ->required(),
                    ]),
            ])
            ->statePath('data');
    }

    public function submit(): void
    {
        $data = $this->form->getState();
        $engine = app(SanaaEngineService::class);

        $payload = [
            'provider' => $data['provider'] ?? 'auto',
            'claude_source' => $data['claude_source'] ?? 'anthropic',
            'auto_provider_order' => $data['auto_provider_order'] ?? 'groq,anthropic,openrouter,local',
            'models' => $data['models'] ?? [],
            'keys' => [
                'anthropic' => trim((string) ($data['keys']['anthropic'] ?? '')),
                'groq' => trim((string) ($data['keys']['groq'] ?? '')),
                'openrouter' => trim((string) ($data['keys']['openrouter'] ?? '')),
            ],
        ];

        $success = $engine->updateBrainConfig($payload);
        
        if ($success) {
            Notification::make()
                ->title('Brain configuration updated')
                ->body('Claude/Groq/OpenRouter brain source settings were saved and applied.')
                ->success()
                ->send();
        } else {
            Notification::make()
                ->title('Failed to update brain configuration')
                ->danger()
                ->send();
        }
    }
}
