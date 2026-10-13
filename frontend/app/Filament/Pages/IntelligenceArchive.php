<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use App\Services\WhatsAppService;
use App\Support\MediaIntelligencePdfs;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Illuminate\Support\Str;

class IntelligenceArchive extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-archive-box';

    protected static string $view = 'filament.pages.intelligence-archive';

    protected static ?string $navigationGroup = 'Intelligence';

    protected static ?int $navigationSort = 2;

    public array $briefings = [];

    public ?array $selectedBriefing = null;

    public ?array $latestSignal = null;

    public string $whatsAppPhone = '';

    public function mount()
    {
        $this->refreshData();
    }

    public function refreshData()
    {
        $engine = app(SanaaEngineService::class);
        $this->briefings = $engine->getBriefings();
        $this->latestSignal = $engine->getLatestSignal();

        if (! $this->selectedBriefing && ! empty($this->briefings[0]['id'])) {
            $this->selectBriefing((int) $this->briefings[0]['id']);
        }
    }

    public function selectBriefing(int $id)
    {
        $engine = app(SanaaEngineService::class);
        $this->selectedBriefing = $engine->getBriefing($id);
    }

    public function closeBriefing()
    {
        $this->selectedBriefing = null;
    }

    public function getSelectedBriefingMetadata(): array
    {
        return $this->selectedBriefing['metadata'] ?? [];
    }

    public function getSelectedBriefingTopics(): array
    {
        return $this->getSelectedBriefingMetadata()['topics'] ?? [];
    }

    public function getSelectedPdfUrl(): ?string
    {
        return $this->selectedBriefing ? MediaIntelligencePdfs::urlForBriefing($this->selectedBriefing) : null;
    }

    public function getSelectedPdfFilename(): ?string
    {
        return $this->selectedBriefing ? MediaIntelligencePdfs::filenameForBriefing($this->selectedBriefing) : null;
    }

    public function getSelectedWhatsappText(): string
    {
        if (! $this->selectedBriefing) {
            return '';
        }

        $title = (string) ($this->selectedBriefing['title'] ?? 'Sanaa Media Intelligence');
        $date = $this->selectedBriefing['created_at'] ? now()->parse($this->selectedBriefing['created_at'])->format('d M Y') : now()->format('d M Y');
        $signals = $this->getSelectedTopSignals();
        $topSignal = $signals[0] ?? Str::limit(strip_tags((string) str($this->selectedBriefing['content'] ?? '')->markdown()), 220);

        return trim("*Sanaa Media Intelligence*\n{$date}\n\n*{$title}*\n{$topSignal}\n\nPDF attached for the full executive briefing.");
    }

    public function shareSelectedBriefingToWhatsApp(): void
    {
        if (! $this->selectedBriefing) {
            Notification::make()->title('Select a briefing first')->warning()->send();

            return;
        }

        $phone = trim($this->whatsAppPhone);
        if ($phone === '') {
            Notification::make()->title('Enter a WhatsApp number')->warning()->send();

            return;
        }

        $whatsApp = app(WhatsAppService::class);
        $caption = $this->getSelectedWhatsappText();
        $pdfUrl = MediaIntelligencePdfs::temporarySignedUrlForBriefing($this->selectedBriefing);
        $result = $pdfUrl
            ? $whatsApp->sendMedia($phone, $pdfUrl, 'document', $caption)
            : $whatsApp->sendMessage($phone, $caption);

        $success = (bool) ($result['success'] ?? false)
            || in_array($result['status'] ?? null, ['success', 'sent', 'queued'], true);

        $notification = Notification::make()
            ->title($success ? 'Briefing shared to WhatsApp' : 'WhatsApp share failed')
            ->body($success ? 'The briefing was sent through the WhatsApp bridge.' : ($result['error'] ?? 'The WhatsApp bridge did not confirm delivery.'));

        $success ? $notification->success() : $notification->danger();
        $notification->send();
    }

    public function getSelectedTopSignals(): array
    {
        $content = (string) ($this->selectedBriefing['content'] ?? '');

        if ($content === '') {
            return [];
        }

        if (! preg_match('/##\s*TOP STRATEGIC SIGNALS(.*?)(?=^##\s|\z)/ims', $content, $matches)) {
            return [];
        }

        $signals = [];
        foreach (preg_split('/\R/', trim($matches[1])) as $line) {
            $line = trim($line);
            if (! str_starts_with($line, '-')) {
                continue;
            }

            $signals[] = trim(ltrim($line, '- '));
        }

        return array_values(array_filter($signals));
    }

    public function getSelectedSections(): array
    {
        $content = (string) ($this->selectedBriefing['content'] ?? '');

        if ($content === '') {
            return [];
        }

        preg_match_all('/^###\s+(.+)$/m', $content, $matches);

        return array_values(array_filter($matches[1] ?? [], function (string $section): bool {
            return stripos($section, 'whatsapp') === false;
        }));
    }
}
