<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class WhatsAppService
{
    protected string $baseUrl;
    protected string $apiKey;

    public function __construct()
    {
        $this->baseUrl = config('services.sanaa_engine.url', 'http://127.0.0.1:8101/api');
        $this->apiKey = config('services.whatsapp.key', '');
    }

    /**
     * Get WhatsJet connection status.
     */
    public function getStatus(): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/whatsapp/status");
            return $response->json() ?? ['healthy' => false];
        } catch (\Exception $e) {
            Log::error("WhatsApp Status Error: " . $e->getMessage());
            return ['healthy' => false, 'error' => $e->getMessage()];
        }
    }

    /**
     * Send a text message.
     */
    public function sendMessage(string $phone, string $message): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(30)
                ->post("{$this->baseUrl}/whatsapp/send-message", [
                    'phone' => $phone,
                    'message' => $message,
                ]);
            return $response->json() ?? ['error' => 'No response'];
        } catch (\Exception $e) {
            Log::error("WhatsApp Send Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Send a media message.
     */
    public function sendMedia(string $phone, string $mediaUrl, string $type = 'image', string $caption = ''): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(30)
                ->post("{$this->baseUrl}/whatsapp/send-media", [
                    'phone' => $phone,
                    'media_url' => $mediaUrl,
                    'type' => $type,
                    'caption' => $caption,
                ]);
            return $response->json() ?? ['error' => 'No response'];
        } catch (\Exception $e) {
            Log::error("WhatsApp Media Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Send a template message.
     */
    public function sendTemplate(string $phone, string $templateName, string $languageCode = 'en', array $components = []): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(30)
                ->post("{$this->baseUrl}/whatsapp/send-template", [
                    'phone' => $phone,
                    'template_name' => $templateName,
                    'language_code' => $languageCode,
                    'components' => $components,
                ]);
            return $response->json() ?? ['error' => 'No response'];
        } catch (\Exception $e) {
            Log::error("WhatsApp Template Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    /**
     * List contacts.
     */
    public function getContacts(int $page = 1, int $limit = 25): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->get("{$this->baseUrl}/whatsapp/contacts", [
                    'page' => $page,
                    'limit' => $limit,
                ]);
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("WhatsApp Contacts Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Get a single contact.
     */
    public function getContact(string $phone): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/whatsapp/contacts/{$phone}");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("WhatsApp Contact Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Create a contact.
     */
    public function createContact(string $phone, string $name = '', array $groups = []): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->post("{$this->baseUrl}/whatsapp/contacts", [
                    'phone' => $phone,
                    'name' => $name,
                    'groups' => $groups,
                ]);
            return $response->json() ?? ['error' => 'No response'];
        } catch (\Exception $e) {
            Log::error("WhatsApp Create Contact Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }
}
