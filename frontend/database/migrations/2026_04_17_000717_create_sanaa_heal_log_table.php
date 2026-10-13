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
        Schema::create('sanaa_heal_log', function (Blueprint $table) {
            $table->id();
            $table->string('app');
            $table->string('tenant')->nullable();
            $table->jsonb('flags');
            $table->text('diagnosis')->nullable();
            $table->text('recommended_action')->nullable();
            $table->jsonb('actions_taken')->nullable();
            $table->boolean('healed')->default(false);
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('sanaa_heal_log');
    }
};
