<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use App\Support\MediaIntelligencePdfs;
use Filament\Forms\Components\Section;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Forms\Concerns\InteractsWithForms;
use Filament\Forms\Contracts\HasForms;
use Filament\Forms\Form;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class NewsIntelligenceSettings extends Page implements HasForms
{
    use InteractsWithForms;

    protected static ?string $navigationIcon = 'heroicon-o-globe-alt';

    protected static ?string $navigationGroup = 'Intelligence';

    protected static ?int $navigationSort = 3;

    protected static string $view = 'filament.pages.news-intelligence-settings';

    protected static ?string $title = 'News & Intelligence';

    public ?array $data = [];

    public ?array $latestBriefing = null;

    public ?array $latestSignal = null;

    public ?array $briefingQa = null;

    public function mount(): void
    {
        $this->refreshOverview();
        $this->loadPreferences();
    }

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Section::make('Intelligence Briefings Delivery')
                    ->description('Configure the Sanaa Media email, PDF attachment, and WhatsApp briefing delivery.')
                    ->columns([
                        'default' => 1,
                        'md' => 2,
                    ])
                    ->schema([
                        Toggle::make('auto_delivery')
                            ->label('Enable Automated Daily Briefings')
                            ->helperText('Generate and send the daily executive summary automatically.'),
                        TextInput::make('delivery_time')
                            ->label('Delivery Time (EAT)')
                            ->type('time')
                            ->required(),
                        TextInput::make('email_recipients')
                            ->label('Sanaa Media Email Recipients')
                            ->placeholder('media@sanaa.co, banks@sanaa.co')
                            ->helperText('Comma-separated email addresses for the daily Sanaa Media briefing.')
                            ->columnSpanFull(),
                        Toggle::make('pdf_attachment')
                            ->label('Attach Executive PDF')
                            ->helperText('Generate the PDF and attach it to the email edition.'),
                        Toggle::make('whatsapp_delivery')
                            ->label('Send WhatsApp Digest')
                            ->helperText('Send the mobile summary through the WhatsApp bridge.'),
                        TextInput::make('whatsapp_recipients')
                            ->label('WhatsApp Recipients')
                            ->placeholder('2567..., 2567...')
                            ->helperText('Comma-separated WhatsApp numbers for the daily mobile digest.')
                            ->columnSpanFull(),
                    ]),
            ])
            ->statePath('data');
    }

    public function loadPreferences(): void
    {
        $engine = app(SanaaEngineService::class);
        $prefs = $engine->getPreferences([
            'news.auto_delivery',
            'news.delivery_time',
            'news.email_recipients',
            'news.whatsapp_enabled',
            'news.whatsapp_recipients',
            'news.pdf_enabled',
            'alert.recipients',
        ]);

        $this->form->fill([
            'auto_delivery' => $this->preferenceEnabled($prefs['news.auto_delivery'] ?? null, true),
            'delivery_time' => $this->preferenceString($prefs['news.delivery_time'] ?? null, '07:15'),
            'email_recipients' => $this->preferenceString(
                $prefs['news.email_recipients'] ?? null,
                $this->preferenceString($prefs['alert.recipients'] ?? null, '')
            ),
            'pdf_attachment' => $this->preferenceEnabled($prefs['news.pdf_enabled'] ?? null, true),
            'whatsapp_delivery' => $this->preferenceEnabled($prefs['news.whatsapp_enabled'] ?? null, true),
            'whatsapp_recipients' => $this->preferenceString($prefs['news.whatsapp_recipients'] ?? null, ''),
        ]);
    }

    public function submit(): void
    {
        $data = $this->form->getState();
        $engine = app(SanaaEngineService::class);

        $engine->updatePreference('news.auto_delivery', $data['auto_delivery']);
        $engine->updatePreference('news.delivery_time', $data['delivery_time']);
        $engine->updatePreference('news.email_recipients', $this->normalizeCsv($data['email_recipients'] ?? ''));
        $engine->updatePreference('news.pdf_enabled', (bool) ($data['pdf_attachment'] ?? true));
        $engine->updatePreference('news.whatsapp_enabled', (bool) ($data['whatsapp_delivery'] ?? true));
        $engine->updatePreference('news.whatsapp_recipients', $this->normalizeCsv($data['whatsapp_recipients'] ?? ''));

        Notification::make()
            ->title('Intelligence Settings Saved')
            ->body('Sanaa Media email, PDF, and WhatsApp delivery preferences are now synced.')
            ->success()
            ->send();

        $this->refreshOverview();
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

        $this->refreshOverview();
    }

    public function refreshOverview(): void
    {
        $engine = app(SanaaEngineService::class);

        $briefings = $engine->getBriefings(1);
        $this->latestBriefing = ! empty($briefings[0]) ? $briefings[0] : null;

        $signal = $engine->getLatestSignal();
        $this->latestSignal = isset($signal['title']) ? $signal : null;

        $qa = $engine->getLatestBriefingQa();
        $this->briefingQa = ! empty($qa) && ! isset($qa['message']) ? $qa : null;
    }

    public function getLatestBriefingPdfUrl(): ?string
    {
        return $this->latestBriefing ? MediaIntelligencePdfs::urlForBriefing($this->latestBriefing) : null;
    }

    public function getLatestBriefingPdfFilename(): ?string
    {
        return $this->latestBriefing ? MediaIntelligencePdfs::filenameForBriefing($this->latestBriefing) : null;
    }

    private function preferenceEnabled($value, bool $default): bool
    {
        if ($value === null || $value === '') {
            return $default;
        }

        if (is_bool($value)) {
            return $value;
        }

        return ! in_array(strtolower((string) $value), ['0', 'false', 'no', 'off', 'disabled'], true);
    }

    private function preferenceString($value, string $fallback): string
    {
        if (is_array($value)) {
            return implode(', ', array_filter(array_map('trim', $value)));
        }

        $string = trim((string) ($value ?? ''));

        return $string === '' ? $fallback : $string;
    }

    private function normalizeCsv(string $value): string
    {
        return implode(', ', array_filter(array_map('trim', explode(',', $value))));
    }
}
