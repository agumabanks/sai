<?php

namespace App\Filament\Pages;

use Filament\Pages\Page;
use Filament\Forms\Contracts\HasForms;
use Filament\Forms\Concerns\InteractsWithForms;
use Filament\Forms\Form;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Forms\Components\Section;
use Filament\Forms\Components\Repeater;
use Filament\Notifications\Notification;
use App\Services\SanaaEngineService;

class NewsIntelligenceSettings extends Page implements HasForms
{
    use InteractsWithForms;

    protected static ?string $navigationIcon = 'heroicon-o-globe-alt';
    protected static ?string $navigationGroup = 'Intelligence';
    protected static ?int $navigationSort = 2;
    protected static string $view = 'filament.pages.news-intelligence-settings';
    protected static ?string $title = 'News & Intelligence';

    public ?array $data = [];

    public function mount(): void
    {
        $this->form->fill([
            'auto_delivery' => true,
            'delivery_time' => '07:00',
        ]);
    }

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Section::make('Intelligence Briefings Delivery')
                    ->description('Configure how and when the daily intelligence reports are dispatched.')
                    ->schema([
                        Toggle::make('auto_delivery')
                            ->label('Enable Automated Daily Briefings')
                            ->helperText('Generate and send the daily executive summary automatically.'),
                        TextInput::make('delivery_time')
                            ->label('Delivery Time (EAT)')
                            ->type('time')
                            ->required(),
                    ]),
            ])
            ->statePath('data');
    }

    public function submit(): void
    {
        $data = $this->form->getState();
        $engine = app(SanaaEngineService::class);
        
        $engine->updatePreference('news.auto_delivery', $data['auto_delivery']);
        $engine->updatePreference('news.delivery_time', $data['delivery_time']);
        
        Notification::make()
            ->title('Intelligence Settings Saved')
            ->success()
            ->send();
    }
    
    public function generateNow(): void
    {
        $engine = app(SanaaEngineService::class);
        $engine->executeCommand('generate briefing');
        
        Notification::make()
            ->title('Briefing generation triggered')
            ->body('The news agent is aggregating and synthesizing RSS feeds. You will receive an email shortly.')
            ->success()
            ->send();
    }
}
