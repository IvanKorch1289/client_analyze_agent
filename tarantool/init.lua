#!/usr/bin/env tarantool

box.cfg({
    listen = 3302,
    memtx_memory = 107374182,
    log_level = 5
})

-- Создаём спейсы, если не существуют
if not box.space.cache then
    box.schema.space.create('cache', { if_not_exists = true })
    box.space.cache:create_index('primary', { parts = {1, 'string'}, if_not_exists = true, unique = true })
    box.space.cache:create_index('expires', { parts = {3, 'number'}, if_not_exists = true })
end

if not box.space.persistent then
    box.schema.space.create('persistent', { if_not_exists = true })
    box.space.persistent:create_index('primary', { parts = {1, 'string'}, if_not_exists = true, unique = true })
end

print("✅ Tarantool инициализирован. Спейсы 'cache' и 'persistent' готовы.")