<?php

namespace Tests\Feature;

use App\Filament\Pages\IntelligenceArchive;
use App\Filament\Pages\NewsIntelligenceSettings;
use App\Models\User;
use App\Services\SanaaEngineService;
use App\Services\WhatsAppService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class IntelligencePagesTest extends TestCase
{
    use RefreshDatabase;

    private string $pdfFilename = 'Sanaa_Media_News_2099_12_31.pdf';

    private function pdfPath(): string
    {
        return dirname(base_path()).'/data/news/'.$this->pdfFilename;
    }

    private function createPdfFixture(): void
    {
        $dir = dirname($this->pdfPath());

        if (! is_dir($dir)) {
            mkdir($dir, 0775, true);
        }

        file_put_contents($this->pdfPath(), "%PDF-1.4\n% test pdf\n");
    }

    private function removePdfFixture(): void
    {
        if (is_file($this->pdfPath())) {
            unlink($this->pdfPath());
        }
    }

    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getBriefings(int $limit = 20): array
            {
                return [[
                    'id' => 1,
                    'title' => 'Daily Briefing - 2099-12-31',
                    'created_at' => '2099-12-31T07:15:00+00:00',
                    'metadata' => ['article_count' => 12, 'topics' => ['Finance', 'Uganda/EAC']],
                    'pdf_path' => null,
                ]];
            }

            public function getBriefing(int $id): array
            {
                return [
                    'id' => $id,
                    'title' => 'Daily Briefing - 2099-12-31',
                    'created_at' => '2099-12-31T07:15:00+00:00',
                    'metadata' => ['article_count' => 12, 'topics' => ['Finance', 'Uganda/EAC']],
                    'pdf_path' => null,
                    'content' => "## TOP STRATEGIC SIGNALS\n- Regional finance signal with board impact\n\n### Finance\nBriefing content.",
                ];
            }

            public function getLatestSignal(): array
            {
                return ['title' => 'Regional finance signal', 'score' => 8];
            }

            public function getLatestBriefingQa(): array
            {
                return ['score' => 9, 'summary' => 'Briefing passed QA'];
            }

            public function getPreferences(array $keys): array
            {
                return [
                    'news.auto_delivery' => true,
                    'news.delivery_time' => '07:15',
                    'news.email_recipients' => 'media@sanaa.co',
                    'news.pdf_enabled' => true,
                    'news.whatsapp_enabled' => true,
                    'news.whatsapp_recipients' => '256700000000',
                ];
            }

            public function updatePreference(string $key, $value): bool
            {
                return true;
            }

            public function executeCommand(string $command): array
            {
                return ['status' => 'started'];
            }
        });
    }

    public function test_intelligence_archive_exposes_pdf_and_whatsapp_share(): void
    {
        $this->stubEngine();
        $this->createPdfFixture();
        $this->instance(WhatsAppService::class, new class extends WhatsAppService
        {
            public function __construct() {}

            public function sendMedia(string $phone, string $mediaUrl, string $type = 'image', string $caption = ''): array
            {
                return ['success' => true, 'phone' => $phone, 'media_url' => $mediaUrl, 'type' => $type];
            }
        });

        try {
            $user = User::factory()->create();

            Livewire::actingAs($user)
                ->test(IntelligenceArchive::class)
                ->assertSee('Download PDF')
                ->assertSee('WhatsApp Share')
                ->set('whatsAppPhone', '256700000000')
                ->call('shareSelectedBriefingToWhatsApp')
                ->assertHasNoErrors();
        } finally {
            $this->removePdfFixture();
        }
    }

    public function test_news_settings_loads_and_saves_media_delivery_preferences(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(NewsIntelligenceSettings::class)
            ->assertSet('data.email_recipients', 'media@sanaa.co')
            ->assertSet('data.whatsapp_recipients', '256700000000')
            ->set('data.email_recipients', 'media@sanaa.co, editor@sanaa.co')
            ->call('submit')
            ->assertHasNoErrors();
    }

    public function test_authenticated_users_can_open_archived_pdf(): void
    {
        $this->createPdfFixture();

        try {
            $user = User::factory()->create();

            $this->actingAs($user)
                ->get(route('media-intelligence.pdf', ['filename' => $this->pdfFilename]))
                ->assertOk()
                ->assertHeader('content-type', 'application/pdf');
        } finally {
            $this->removePdfFixture();
        }
    }
}
