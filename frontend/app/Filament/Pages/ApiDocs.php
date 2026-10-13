<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class ApiDocs extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-document-text';

    protected static ?string $navigationGroup = 'System';

    protected static ?int $navigationSort = 25;

    protected static string $view = 'filament.pages.api-docs';

    protected static ?string $title = 'API Documentation';

    protected static ?string $navigationLabel = 'API Docs';

    protected static ?string $slug = 'api-docs';

    // ── Page state ────────────────────────────────────────────────────────

    /** Full OpenAPI specification */
    public array $spec = [];

    /** Tracks which endpoint details are expanded */
    public array $expandedEndpoints = [];

    // ── Lifecycle ─────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadSpec();
    }

    // ── Data loading ──────────────────────────────────────────────────────

    public function loadSpec(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->spec = $engine->getOpenApiSpec();
    }

    // ── Actions ───────────────────────────────────────────────────────────

    public function refreshSpec(): void
    {
        $this->loadSpec();
        Notification::make()->title('API spec refreshed')->success()->send();
    }

    public function toggleEndpoint(string $path, string $method): void
    {
        $key = "{$path}.{$method}";

        if (isset($this->expandedEndpoints[$key]) && $this->expandedEndpoints[$key]) {
            $this->expandedEndpoints[$key] = false;
        } else {
            $this->expandedEndpoints[$key] = true;
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    /**
     * Get the API info section.
     */
    public function getApiInfo(): array
    {
        return $this->spec['info'] ?? [];
    }

    /**
     * Get the OpenAPI version.
     */
    public function getOpenApiVersion(): string
    {
        return $this->spec['openapi'] ?? 'unknown';
    }

    /**
     * Get all paths from the spec.
     */
    public function getPaths(): array
    {
        return $this->spec['paths'] ?? [];
    }

    /**
     * Count total endpoints across all paths.
     */
    public function getEndpointCount(): int
    {
        $count = 0;
        foreach ($this->getPaths() as $methods) {
            $count += count($methods);
        }

        return $count;
    }

    /**
     * Get CSS classes for an HTTP method badge.
     */
    public function getMethodBadge(string $method): string
    {
        return match (strtoupper($method)) {
            'GET' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
            'POST' => 'text-[#0a84ff] bg-[#0a84ff]/10 border-[#0a84ff]/20',
            'PUT' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
            'PATCH' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
            'DELETE' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
            'HEAD' => 'text-[#bf5af2] bg-[#bf5af2]/10 border-[#bf5af2]/20',
            'OPTIONS' => 'text-white/40 bg-white/5 border-white/10',
            default => 'text-white/40 bg-white/5 border-white/10',
        };
    }

    /**
     * Check if an endpoint detail section is expanded.
     */
    public function isExpanded(string $path, string $method): bool
    {
        $key = "{$path}.{$method}";

        return $this->expandedEndpoints[$key] ?? false;
    }

    /**
     * Get unique tags from the spec paths.
     */
    public function getTags(): array
    {
        $tags = [];
        foreach ($this->getPaths() as $methods) {
            foreach ($methods as $detail) {
                if (isset($detail['tags'])) {
                    foreach ($detail['tags'] as $tag) {
                        $tags[$tag] = true;
                    }
                }
            }
        }

        return array_keys($tags);
    }

    /**
     * Get security schemes from the spec.
     */
    public function getSecuritySchemes(): array
    {
        return $this->spec['components']['securitySchemes'] ?? [];
    }

    /**
     * Format a JSON schema for display.
     */
    public function formatSchema(array $schema): string
    {
        return json_encode($schema, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    }
}
