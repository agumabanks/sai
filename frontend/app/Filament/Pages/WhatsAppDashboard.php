<?php

namespace App\Filament\Pages;

use App\Services\WhatsAppService;
use Filament\Pages\Page;
use Filament\Notifications\Notification;

class WhatsAppDashboard extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-chat-bubble-left-right';

    protected static string $view = 'filament.pages.whatsapp-dashboard';

    protected static ?string $navigationGroup = 'Channels';

    protected static ?string $title = 'WhatsApp';

    protected static ?int $navigationSort = 10;

    public array $status = [];
    public array $contacts = [];
    public string $sendPhone = '';
    public string $sendMessage = '';
    public bool $showSendModal = false;

    public function mount()
    {
        $this->refreshStatus();
    }

    public function refreshStatus()
    {
        $wa = app(WhatsAppService::class);
        $this->status = $wa->getStatus();
    }

    public function loadContacts()
    {
        $wa = app(WhatsAppService::class);
        $result = $wa->getContacts();
        $this->contacts = $result['data'] ?? $result['contacts'] ?? [];
    }

    public function openSendModal()
    {
        $this->showSendModal = true;
    }

    public function closeSendModal()
    {
        $this->showSendModal = false;
        $this->sendPhone = '';
        $this->sendMessage = '';
    }

    public function sendTestMessage()
    {
        if (empty($this->sendPhone) || empty($this->sendMessage)) {
            Notification::make()
                ->title('Missing Fields')
                ->body('Phone number and message are required.')
                ->warning()
                ->send();
            return;
        }

        $wa = app(WhatsAppService::class);
        $result = $wa->sendMessage($this->sendPhone, $this->sendMessage);

        if (isset($result['error'])) {
            Notification::make()
                ->title('Send Failed')
                ->body($result['error'])
                ->danger()
                ->send();
        } else {
            Notification::make()
                ->title('Message Sent')
                ->body("Message delivered to {$this->sendPhone}")
                ->success()
                ->send();
            $this->closeSendModal();
        }
    }

    public function openAdmin()
    {
        $this->redirect(config('services.whatsapp.admin_url', 'https://wa.sanaa.co'));
    }
}
