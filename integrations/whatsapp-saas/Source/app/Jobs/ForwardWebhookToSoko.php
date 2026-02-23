<?php

namespace App\Jobs;

use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class ForwardWebhookToSoko implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $tries = 3;
    public int $backoff = 5;

    protected string $type; // 'delivery' or 'incoming'
    protected array $payload;
    protected int $vendorId;

    public function __construct(string $type, array $payload, int $vendorId)
    {
        $this->type = $type;
        $this->payload = $payload;
        $this->vendorId = $vendorId;
        $this->onQueue('default');
    }

    public function handle(): void
    {
        if (!config('services.soko_webhook_enabled', false)) {
            return;
        }

        // Check if this vendor is linked to Soko
        $vendorUid = $this->getVendorUid();
        if (!$vendorUid) {
            return;
        }

        $sellerUuid = $this->getVendorSetting('soko_seller_uuid');
        if (!$sellerUuid) {
            return;
        }

        $this->payload['vendor_uid'] = $vendorUid;

        $baseUrl = rtrim(config('services.soko_webhook_url', 'https://soko.sanaa.ug/api/webhooks/whatsapp'), '/');
        $url = "{$baseUrl}/{$this->type}";
        $secret = config('services.soko_webhook_secret', '');

        $jsonPayload = json_encode($this->payload);
        $signature = hash_hmac('sha256', $jsonPayload, $secret);

        try {
            $response = Http::withHeaders([
                'X-Webhook-Signature' => $signature,
                'Content-Type' => 'application/json',
            ])
                ->timeout(10)
                ->withBody($jsonPayload, 'application/json')
                ->post($url);

            if (!$response->successful()) {
                Log::warning('Soko webhook forward failed', [
                    'type' => $this->type,
                    'vendor_id' => $this->vendorId,
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);
            }
        } catch (\Exception $e) {
            Log::error('Soko webhook forward error', [
                'type' => $this->type,
                'vendor_id' => $this->vendorId,
                'error' => $e->getMessage(),
            ]);
            throw $e; // Re-throw to trigger retry
        }
    }

    protected function getVendorUid(): ?string
    {
        $vendor = \App\Yantrana\Components\Vendor\Models\VendorModel::find($this->vendorId);
        return $vendor?->_uid;
    }

    protected function getVendorSetting(string $name): ?string
    {
        $setting = \App\Yantrana\Components\Vendor\Models\VendorSettingsModel::where('vendors__id', $this->vendorId)
            ->where('name', $name)
            ->first();
        return $setting?->value;
    }
}
