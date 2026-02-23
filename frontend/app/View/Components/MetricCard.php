<?php

namespace App\View\Components;

use Illuminate\View\Component;
use Illuminate\View\View;

class MetricCard extends Component
{
    public function __construct(
        public string $label,
        public string $value,
        public ?string $icon = null,
        public ?string $description = null,
        public ?string $trend = null,
        public ?string $color = 'indigo',
        public ?string $size = 'default'
    ) {}

    public function render(): View
    {
        return view('components.metric-card');
    }

    public function colorClasses(): string
    {
        return match($this->color) {
            'indigo' => 'text-sanaa-indigo border-sanaa-indigo/20 bg-sanaa-indigo/5',
            'emerald' => 'text-sanaa-emerald border-sanaa-emerald/20 bg-sanaa-emerald/5',
            'cyan' => 'text-sanaa-cyan border-sanaa-cyan/20 bg-sanaa-cyan/5',
            'purple' => 'text-sanaa-purple border-sanaa-purple/20 bg-sanaa-purple/5',
            'red' => 'text-red-500 border-red-500/20 bg-red-500/5',
            'amber' => 'text-sanaa-amber border-sanaa-amber/20 bg-sanaa-amber/5',
            default => 'text-sanaa-indigo border-sanaa-indigo/20 bg-sanaa-indigo/5',
        };
    }

    public function iconColorClasses(): string
    {
        return match($this->color) {
            'indigo' => 'text-sanaa-indigo',
            'emerald' => 'text-sanaa-emerald',
            'cyan' => 'text-sanaa-cyan',
            'purple' => 'text-sanaa-purple',
            'red' => 'text-red-500',
            'amber' => 'text-sanaa-amber',
            default => 'text-sanaa-indigo',
        };
    }

    public function glowClasses(): string
    {
        return match($this->color) {
            'indigo' => 'shadow-[0_0_20px_rgba(99,102,241,0.2)]',
            'emerald' => 'shadow-[0_0_20px_rgba(16,185,129,0.2)]',
            'cyan' => 'shadow-[0_0_20px_rgba(6,182,212,0.2)]',
            'purple' => 'shadow-[0_0_20px_rgba(139,92,246,0.2)]',
            'red' => 'shadow-[0_0_20px_rgba(239,68,68,0.2)]',
            'amber' => 'shadow-[0_0_20px_rgba(245,158,11,0.2)]',
            default => 'shadow-[0_0_20px_rgba(99,102,241,0.2)]',
        };
    }
}
