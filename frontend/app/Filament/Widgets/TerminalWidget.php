<?php

namespace App\Filament\Widgets;

use Filament\Widgets\Widget;

class TerminalWidget extends Widget
{
    protected static string $view = 'filament.widgets.terminal-widget';

    protected static bool $isLazy = false;

    // Full width
    protected int | string | array $columnSpan = 'full';
}
