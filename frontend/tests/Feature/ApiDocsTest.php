<?php

namespace Tests\Feature;

use App\Filament\Pages\ApiDocs;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class ApiDocsTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub the SanaaEngineService to avoid real backend API calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getOpenApiSpec(): array
            {
                return [
                    'openapi' => '3.1.0',
                    'info' => [
                        'title' => 'Sanaa AI Engine',
                        'version' => '2.0.0',
                        'description' => 'Autonomous Intelligence Platform API',
                    ],
                    'paths' => [
                        '/api/health' => [
                            'get' => [
                                'summary' => 'Health Check',
                                'description' => 'Returns system health status',
                                'responses' => [
                                    '200' => ['description' => 'OK'],
                                ],
                            ],
                        ],
                        '/api/skills' => [
                            'get' => [
                                'summary' => 'List Skills',
                                'description' => 'Returns all registered skills',
                                'responses' => [
                                    '200' => ['description' => 'OK'],
                                ],
                            ],
                        ],
                        '/api/command' => [
                            'post' => [
                                'summary' => 'Execute Command',
                                'description' => 'Sends a command to the AI engine',
                                'requestBody' => [
                                    'content' => [
                                        'application/json' => [
                                            'schema' => [
                                                'type' => 'object',
                                                'properties' => [
                                                    'message' => ['type' => 'string'],
                                                ],
                                            ],
                                        ],
                                    ],
                                ],
                                'responses' => [
                                    '200' => ['description' => 'OK'],
                                ],
                            ],
                        ],
                        '/api/tenants' => [
                            'get' => [
                                'summary' => 'List Tenants',
                                'description' => 'Returns all registered tenants',
                                'responses' => [
                                    '200' => ['description' => 'OK'],
                                ],
                            ],
                        ],
                    ],
                    'components' => [
                        'schemas' => [],
                        'securitySchemes' => [
                            'BearerAuth' => [
                                'type' => 'http',
                                'scheme' => 'bearer',
                            ],
                        ],
                    ],
                ];
            }
        });
    }

    public function test_page_loads(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->assertSuccessful();
    }

    public function test_displays_api_title(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->assertSee('API Documentation')
            ->assertSee('Sanaa AI Engine');
    }

    public function test_displays_api_version(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->assertSee('2.0.0');
    }

    public function test_displays_endpoints(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->assertSee('/api/health')
            ->assertSee('/api/skills')
            ->assertSee('/api/command')
            ->assertSee('/api/tenants');
    }

    public function test_displays_http_methods(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->assertSee('GET')
            ->assertSee('POST');
    }

    public function test_displays_endpoint_summaries(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->assertSee('Health Check')
            ->assertSee('List Skills')
            ->assertSee('Execute Command');
    }

    public function test_navigation_registered(): void
    {
        $this->assertEquals('System', ApiDocs::getNavigationGroup());
        $this->assertEquals('heroicon-o-document-text', ApiDocs::getNavigationIcon());
    }

    public function test_page_slug(): void
    {
        $this->assertEquals('api-docs', ApiDocs::getSlug());
    }

    public function test_refresh_spec(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->call('refreshSpec')
            ->assertHasNoErrors();
    }

    public function test_toggle_endpoint_detail(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        $component = Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->call('toggleEndpoint', '/api/health', 'get');

        $expanded = $component->get('expandedEndpoints');
        $this->assertTrue($expanded['/api/health.get'] ?? false);

        $component->call('toggleEndpoint', '/api/health', 'get');
        $expanded = $component->get('expandedEndpoints');
        $this->assertFalse($expanded['/api/health.get'] ?? true);
    }

    public function test_endpoint_count(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(ApiDocs::class)
            ->assertSee('4 endpoints');
    }
}
