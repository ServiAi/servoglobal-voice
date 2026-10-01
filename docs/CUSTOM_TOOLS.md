# Custom HTTP Tools

Permite que un tenant cree, desde `/voice-ai/tools` o la API, herramientas HTTP declarativas que sus agentes `serviglobal_managed` pueden invocar durante una llamada, sin escribir código y sin salir del mecanismo de tools existente.

## Platform Tool vs Custom Tool

| | Platform Tool | Custom Tool |
| --- | --- | --- |
| Namespace | `calendar.*`, `whatsapp.*`, `crm.*`, `handoff.*` | `custom.*` |
| Definida por | Código (`app.modules.tools.domain.registry`) | Tenant, vía UI/API (`tenant_tools` + `tenant_http_tool_configs`) |
| Ejecutada por | Handler Python fijo (`ToolDispatchService._HANDLERS`) | `CustomHttpToolExecutor` (una llamada HTTP declarativa) |
| Disponibilidad | `status="available"` en el Registry + `required_integration` configurada | `status="active"` en `tenant_tools` + credencial configurada (o `auth_type="none"`) |

Ambas se resuelven a un mismo contrato (`ResolvedToolDefinition`, ver `app.modules.tools.domain.resolved_tool`) a través de `ToolResolverService`, y ambas compilan a un `CompiledToolSpec` idéntico en forma (`key/name/description/input_schema`). El runtime de voz (LiveKit) nunca distingue una de otra: registra cualquier `CompiledToolSpec` como la misma `RawFunctionTool` genérica y llama de vuelta al mismo endpoint interno.

## Seguridad

- **Namespace**: `custom.<segmento>` (`[a-z0-9_]{1,60}`), validado en `app.modules.tools.domain.namespace.validate_custom_key` (única fuente de verdad) más un `CHECK` a nivel de base de datos como defensa adicional. Los namespaces de plataforma están reservados y no pueden reutilizarse.
- **Aislamiento multi-tenant**: cada query de `TenantTool`/`TenantHttpToolConfig`/`TenantToolCredential` filtra explícitamente por `tenant_id`, nunca solo por el id de la fila (aunque ese id ya sea único globalmente) — un id cruzado de tenant siempre resuelve a "no encontrado", nunca a un error que confirme su existencia en otro tenant.
- **Cifrado de credenciales**: reutiliza `SecretManagerService` (Fernet, clave derivada de `INTEGRATIONS_ENCRYPTION_KEY`) sin ningún mecanismo criptográfico nuevo — el mismo que ya protege `TenantIntegration.secrets_json_encrypted`. `tenant_tool_credentials.secrets_json_encrypted` es un blob JSON con cada valor cifrado individualmente (la forma varía por `auth_type`: `bearer` → `{token}`, `api_key` → `{api_key}`, `basic` → `{username, password}`).
- **El secreto nunca sale del backend**: ningún endpoint HTTP-facing devuelve un secreto en texto plano; toda respuesta usa `{configured, masked_fields}` (mismo patrón `abcd...wxyz` de `SecretManager.mask_secret`). Sólo `TenantToolCredentialService.resolve_for_execution` descifra, y sólo `CustomHttpToolExecutor` la llama — nunca un módulo de endpoints.
- **El secreto nunca llega al LLM ni al runtime**: `CompiledToolSpec` y `RuntimeSessionSpecV1` nunca contienen `base_url`, `path_template`, cabeceras ni credencial — verificado explícitamente por test (`test_agent_compiler.py::test_compiles_custom_tool_binding_without_leaking_http_config`).
- **Headers**: los headers estáticos configurados por el tenant nunca pueden sobrescribir `Host`, `Authorization`, `Proxy-Authorization`, `Connection`, `Content-Length`, `Transfer-Encoding`, `Cookie` ni `Set-Cookie` — `Authorization` proviene exclusivamente de la credencial resuelta server-side.
- **Auditoría sin PII**: los eventos de `IntegrationEventService` sólo registran `{tool_key, status}` o `{tenant_tool_id, auth_type, action}` — nunca argumentos, endpoint completo, headers ni el cuerpo de la respuesta.

## SSRF y seguridad HTTP (`ToolHttpSecurityService` / `SafeHttpClient`)

`backend/app/modules/tools/infrastructure/http_safety.py` implementa la única vía de salida HTTP para una Custom Tool:

1. **Scheme**: sólo `https` en producción (`http` requiere `CUSTOM_TOOLS_ALLOW_HTTP=true`, apagado por defecto, pensado sólo para desarrollo local).
2. **Sin credenciales en la URL** (`user:pass@host` se rechaza) y sólo puertos `80`/`443`.
3. **Resolución DNS explícita**: `socket.getaddrinfo(hostname, port)` antes de conectar, contra **todas** las IPs devueltas (IPv4 e IPv6).
4. **Validación de cada IP**: se rechaza si es `is_private`/`is_loopback`/`is_link_local`/`is_multicast`/`is_reserved`/`is_unspecified`, o si es literalmente `169.254.169.254` (metadata cloud). Si **cualquier** IP de la respuesta DNS es insegura, se rechaza toda la petición — nunca "usar la primera IP buena", que es exactamente el patrón vulnerable a DNS rebinding.
5. **Conexión pineada**: la conexión real se hace contra la IP ya validada (host de la URL sustituido por la IP literal), mientras la cabecera `Host` y la verificación TLS (SNI, vía la extensión `sni_hostname` de httpx/httpcore) siguen usando el hostname original — así un segundo lookup DNS (que podría devolver una IP distinta, ya insegura) nunca ocurre, y el certificado se sigue validando correctamente contra el dominio real.
6. **Sin redirects automáticos** (`follow_redirects=False`): una respuesta 3xx se trata como fallo, nunca se sigue.
7. **Timeout acotado**: 1s–15s, con 8s por defecto; un valor fuera de rango se recorta al límite, nunca se rechaza silenciosamente ni se deja sin límite.
8. **Tamaño de respuesta acotado**: 1 MiB, cortado en streaming (no se buffers una respuesta completa antes de medirla).
9. **Content-Type restringido**: sólo `application/json` y `text/plain`; cualquier otro (incluido HTML) se rechaza antes de intentar parsear el cuerpo.
10. **TLS siempre verificado**: no existe ningún parámetro, en ningún punto del schema o la API, para desactivar la verificación de certificado.

`SafeHttpClient` no tiene ningún conocimiento de tools, mappings o tenants — es una primitiva "haz una llamada HTTP segura" reutilizable tal cual por un futuro `McpToolExecutor`.

## Mappings declarativos (`app.modules.tools.domain.mapping`)

No hay lenguaje de expresiones ni `eval`: un mapping es un diccionario `{campo: ruta}` donde la ruta es una cadena de segmentos separados por `.`, resuelta por una función que sólo hace *lookups* literales de clave (o índice numérico de lista, sólo permitido en el lado de respuesta).

- **Request** (`path_mapping`/`query_mapping`/`body_mapping`): raíces permitidas `args.*` (argumento que envía el LLM), `context.*` (identidad de sesión: `context.caller.phone`, `context.lead.id`, etc. — igual disciplina que `crm.create_lead`/`calendar.create_booking`, nunca confiado del LLM), `binding.config.*` (configuración fija del binding en el agente). Sin índices de lista.
- **Path**: `path_template` usa placeholders `{nombre}` sustituidos por el valor resuelto de `path_mapping`, URL-encodeado (incluyendo `/` literal) — un valor nunca puede inyectar estructura de ruta adicional, cambiar el host o el scheme.
- **Response** (`response_mapping`): raíz `response.*` sobre el JSON devuelto por la API externa; **sí** permite un segmento numérico como índice de lista (p. ej. `response.results.0.balance`), porque muchas APIs reales devuelven `{"results": [...]}` y prohibirlo por completo haría la notación inútil contra la mayoría de APIs REST — wildcards y slicing siguen sin soportarse (cualquier sintaxis de ese tipo no matchea ningún segmento literal y produce un error controlado).
- Si no se configura `response_mapping`, se devuelve el JSON completo (ya acotado a 1 MiB) o, para `text/plain`, el texto crudo bajo `{"response": "..."}`.

## Flujo de ejecución

```
LLM
 → LiveKit (voice-runtime/tool_dispatcher.py, RawFunctionTool genérico)
 → ControlPlaneClient.invoke_tool()  [JWT interno, un único intento]
 → POST /api/v1/internal/voice-runtime/sessions/{id}/tools/{key}/invoke
 → ToolDispatchService.invoke()
     - revalida sesión no terminal, binding enabled en la versión PUBLICADA real
     - key empieza con "custom." → ToolResolverService.get_active_custom_tool()
       (re-resuelve status="active" del tenant, nunca confía en el spec compilado)
     - CustomHttpToolExecutor.execute()
         - valida arguments contra input_schema (mismo validador que las tools de plataforma)
         - TenantToolCredentialService.resolve_for_execution()  [único punto que descifra]
         - construye path/query/body vía tool_mapping
         - SafeHttpClient.request()  [SSRF, timeout, tamaño, content-type]
         - extract_response_values()  [o JSON/texto completo si no hay mapping]
 → resultado mapeado (dict) vuelve como tool result al LLM
```

`ToolDispatchService.invoke()` nunca cambió su comportamiento para las 4 tools de plataforma existentes: la rama `custom.*` es un guard clause al inicio del método que desvía a `CustomHttpToolExecutor`, dejando el resto del código textualmente intacto.

## Crear una Custom HTTP Tool

1. `/voice-ai/tools` → "Nueva herramienta" (o `POST /api/v1/tools/custom`).
2. Completar identidad (`name`, `key` con prefijo `custom.`, `description`), endpoint (`method`, `base_url`, `path_template`, `timeout_ms`), esquema de entrada (JSON Schema básico: `type/properties/required`), mappings (path/query/body/response) y autenticación (`none`/`bearer`/`api_key`/`basic`).
3. La tool se crea en estado `disabled`.
4. `POST /{tool_id}/activate` — falla si el `auth_type` elegido requiere un secreto que todavía no se configuró.

## Probar una Custom HTTP Tool

`POST /api/v1/tools/custom/{tool_id}/test` con `{"arguments": {...}}` ejecuta el mismo `CustomHttpToolExecutor` que usará el runtime real (no un camino de prueba separado que pueda divergir), sin exigir `status="active"`. Responde `{success, status_code, latency_ms, mapped_result, error_code}` — nunca cabeceras, credenciales ni la URL cruda.

## Asignar a un agente

En Agent Builder (`/voice-ai/agents/{id}`, pestaña "Herramientas"), la sección "Herramientas personalizadas" lista las tools `custom.*` activas del tenant junto a las de plataforma. El binding guardado en `TenantAgentVersion.runtime_binding_json["tools"]` sigue siendo `{key, enabled, config}` — nunca copia `base_url`, mappings ni credencial dentro del agente. Sólo agentes `management_mode="serviglobal_managed"` pueden vincular tools `custom.*`; un agente `provider_managed` las rechaza al guardar el draft (validación genérica ya existente para cualquier tool, no específica de custom).

## Runtime execution — revalidación en profundidad

Antes de ejecutar, el backend confirma (sin confiar en lo que el runtime cree haber compilado):

1. La tool sigue vinculada (`enabled=true`) en el `runtime_binding_json` de la versión **publicada** real de esa sesión.
2. La tool pertenece al tenant de la sesión (`ToolResolverService` filtra por `tenant_id`).
3. La tool está `status="active"` — una tool deshabilitada después de publicar el agente deja de ejecutarse aunque el binding siga diciendo `enabled=true`.

## Feature flag

`custom_http_tools_v1` en `TenantFeatureService` (mismo mecanismo que `agent_builder_v2`), apagado por defecto. Se activa por tenant vía el endpoint admin existente de feature grants.

## Limitaciones conocidas de esta versión

- Sólo `GET`, `POST`, `PUT`, `PATCH`, `DELETE` — sin soporte para multipart/form-data.
- Una credencial es 1:1 con su tool (no existe todavía un "pool" de credenciales reutilizable entre varias tools, aunque el spec original lo sugería como recurso independiente) — simplificación deliberada del MVP.
- La detección de "tool en uso" para `DELETE` escanea en Python las versiones publicadas del tenant (no es una query SQL sobre el JSON) — aceptable a la escala esperada, deuda documentada si el volumen de agentes/tenants crece mucho.
- No hay MCP, webhooks como tipo independiente, ni ejecución de código arbitrario — explícitamente fuera de alcance de este incremento.

## Evolución futura: MCP

El seam quedó diseñado para esto sin rediseño: `ResolvedToolDefinition.source` ganaría una variante `"mcp"`, `ToolResolverService.resolve()` una rama más, y un `McpToolExecutor` se sumaría junto a `CustomHttpToolExecutor` en el fork de `ToolDispatchService.invoke()`. `SafeHttpClient` y `app.modules.tools.domain.mapping` ya son suficientemente genéricos para reutilizarse tal cual como transporte HTTP y shaping de respuesta de MCP. Lo único genuinamente nuevo sería el paso de negociación/descubrimiento de tools propio del protocolo MCP, que poblaría filas de `TenantTool`/config en vez de que el tenant las tipee a mano.
