<?php

namespace App\Filament\Pages;

use Filament\Pages\Page;

class SanaaChat extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-chat-bubble-left-right';

    protected static ?string $navigationLabel = 'Sanaa Chat';

    protected static ?string $title = 'Sanaa Chat';

    protected static ?int $navigationSort = 2;

    protected static string $view = 'filament.pages.sanaa-chat';
}
