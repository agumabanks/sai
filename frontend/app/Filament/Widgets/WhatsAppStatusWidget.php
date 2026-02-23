<?php

namespace App\Filament\Widgets;

use App\Services\WhatsAppService;
use Filament\Widgets\Widget;
use Filament\Notifications\Notification;

class WhatsAppStatusWidget extends Widget
{
    protected static string $view = 'filament.widgets.whatsapp-status-widget';

    protected static bool $isLazy = false;

    protected static ?string $pollingInterval = '30s';

    protected int | string | array $columnSpan = 'full';

    public array $status = [];
    public string $quickPhone = '';
    public string $quickMessage = '';

    public function mount()
    {
        $this->refreshStatus();
    }

    public function refreshStatus()
    {
        $wa = app(WhatsAppService::class);
        $this->status = $wa->getStatus();
    }

    public function quickSend()
    {
        if (empty($this->quickPhone) || empty($this->quickMessage)) {
            Notification::make()
                ->title('Missing Fields')
                ->body('Phone and message required.')
                ->warning()
                ->send();
            return;
        }

        $wa = app(WhatsAppService::class);
        $result = $wa->sendMessage($this->quickPhone, $this->quickMessage);

        if (isset($result['error'])) {
            Notification::make()
                ->title('Send Failed')
                ->body($result['error'])
                ->danger()
                ->send();
        } else {
            Notification::make()
                ->title('Sent')
                ->body("Message delivered to {$this->quickPhone}")
                ->success()
                ->send();
            $this->quickPhone = '';
            $this->quickMessage = '';
        }
    }
}
