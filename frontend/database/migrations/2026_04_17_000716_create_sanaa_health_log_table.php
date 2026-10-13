<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('sanaa_health_log', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->string('app');
            $table->string('tenant')->nullable();
            $table->jsonb('signals');
            $table->integer('score');
            $table->enum('status', ['healthy', 'degraded', 'critical']);
            $table->text('groq_diagnosis')->nullable();
            $table->enum('action_taken', ['none', 'alert_sent', 'heal_triggered'])->default('none');
            $table->jsonb('heal_response')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('sanaa_health_log');
    }
};
