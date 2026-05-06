# Prueba Tecnica - Desarrollador Odoo Senior

**Empresa:** M&S VITAMINS SAS
**Modulo:** Payment Behavior (Odoo 14)
**Duracion:** 2 horas maximo
**Herramientas permitidas:** Documentacion oficial de Odoo, Stack Overflow, modulos OCA/enterprise como referencia, tu IDE.
**Herramientas NO permitidas:** Claude Code, Copilot, ChatGPT, Cursor AI, Gemini, ni ningun asistente de IA generativa.

> **Por que sin IA?** No es desconfianza. En M&S Vitamins ya usamos IA intensivamente y la mayoria del codigo se escribe asistido. Pero precisamente por eso necesitamos que el desarrollador detras del prompt tenga criterio propio para auditar, redirigir y validar lo que la IA produce. Esta prueba mide exactamente eso.
>
> Hay un principio bien establecido en ingenieria de software: *"It's harder to read code than to write it"* (Joel Spolsky). Y otro: *"Debugging is twice as hard as writing the code in the first place"* (Brian Kernighan). Esta prueba te pone en esa situacion — leer codigo ajeno, entender que falla, y proponer que se puede mejorar — que es la tarea mas dificil y mas valiosa que hace un desarrollador senior.

---

## Sobre la empresa

**M&S Vitamins** es una distribuidora de vitaminas y suplementos y fabricante de alimentos en Colombia. Operamos en B2B y B2C: nuestros clientes son drogueras, farmacias y mayoristas tanto como clientes finales a traves de ecommerce. Mas de 50.000 partners activos en el ERP.

El area de **Cartera** gestiona el cobro y el riesgo de credito de esa base de clientes. Su trabajo depende de tener informacion precisa y actualizada sobre como paga cada cliente: si paga a tiempo, con que frecuencia se atrasa, si esta en mora activa. Con esa informacion toman decisiones sobre cupos, condiciones de pago y gestion de cobro.

El modulo sobre el que vas a trabajar vive en esa interseccion: datos de facturacion, comportamiento de pago, y las decisiones que Cartera toma con esa informacion todos los dias.

---

## Setup del Entorno

```bash
# 1. Clonar/descargar este repositorio
# 2. Levantar el entorno
cd docker
docker-compose up -d

# 3. Esperar a que los servicios inicien (~2-3 minutos la primera vez)
#    La base de datos ya incluye datos de prueba pre-cargados
# 4. Acceder a http://localhost:8079
#    Usuario: admin
#    Password: admin

# 5. El modulo payment_behavior ya viene instalado con datos de prueba
```

**MailHog** (testing de emails): http://localhost:8035

**Nota:** Si necesitas reiniciar la base de datos desde cero, elimina los volumenes:
```bash
docker-compose down -v
docker-compose up -d
```

---

## PARTE 1: Tickets de Soporte (60 min)

Resuelve los siguientes tickets. Para cada uno entrega:

1. **Causa raiz** — una frase explicando que esta mal y por que.
2. **Solucion** — el codigo del fix.
3. **Impacto en negocio** — que equipo se ve afectado y que decision toma mal mientras el bug persiste (una frase).

### TICKET #1: "Dias de pago incorrectos en facturas con pagos parciales"

**Reportado por:** Equipo de Cartera
**Prioridad:** Alta

**Descripcion:**
Cuando una factura se paga en multiples cuotas (ej: 50% el dia 10 y 50% el dia 25), el campo "Days to Pay" muestra un valor incorrecto. Parece que toma la fecha del **primer** pago en lugar del **ultimo**.

**Pasos para reproducir:**
1. Crear una factura con fecha 2025-01-01 y vencimiento 2025-01-31
2. Registrar un pago parcial (50%) el 2025-01-15
3. Registrar el pago restante (50%) el 2025-01-28
4. Observar que "Days to Pay" muestra 14 dias en vez de 27

**Contexto de negocio:** Los clientes que pagan en cuotas representan buena parte de la cartera B2B. Si Days to Pay se mide desde el primer pago parcial, el rating y el credit score quedan artificialmente inflados o desinflados.

---

### TICKET #2: "Metricas de pago no se actualizan al registrar pagos"

**Reportado por:** Gerente Comercial
**Prioridad:** Alta

**Descripcion:**
Despues de registrar un pago y reconciliarlo con una factura, las metricas del partner (average_pay_time, percentage_invoices_on_time, rating) no se actualizan inmediatamente. Solo se actualizan al dia siguiente (cuando corre el cron).

**Pasos para reproducir:**
1. Ir a Contactos > seleccionar un partner con facturas
2. Anotar sus metricas actuales en la pestana "Payment Behavior"
3. Registrar un pago para una de sus facturas pendientes
4. Volver al partner y verificar que las metricas NO cambiaron
5. Esperar al dia siguiente (cron) para ver los cambios

**Esperado:** Las metricas deberian actualizarse inmediatamente despues de reconciliar un pago.

**Contexto de negocio:** Comercial revisa el rating antes de aprobar un pedido grande. Si acaban de registrar el pago de una deuda vencida pero el rating todavia dice "Very Poor", pueden bloquear un pedido que ya no deberia estar bloqueado.

---

### TICKET #3: "Timeout al actualizar modulo en produccion"

**Reportado por:** DevOps
**Prioridad:** Critica

**Descripcion:**
Al hacer upgrade del modulo en la base de datos de produccion (que tiene +50,000 partners), el proceso se queda colgado por mas de 30 minutos y eventualmente da timeout.

El error ocurre porque Odoo intenta calcular los campos `payment_status` y `payment_behavior_rating` para TODOS los partners existentes al mismo tiempo durante la instalacion.

**Contexto tecnico:**
- En Odoo, cuando se agrega un campo `stored computed` o un campo `Selection` con `store=True` a un modelo existente, el sistema intenta computar/inicializar el valor para todos los registros existentes.
- Esto causa un problema masivo de rendimiento con +50,000 registros.

**Pista:** Investiga como otros modulos de Odoo manejan la inicializacion de columnas con `_auto_init()` y funciones de `odoo.tools.sql`.

**Contexto de negocio:** Un timeout en upgrade deja el ERP inaccesible durante la ventana de mantenimiento, impactando facturacion, despachos y cartera en tiempo real.

---

### TICKET #4: "Todos los partners aparecen como 'Very Poor' aunque pagan bien"

**Reportado por:** Equipo de Cartera
**Prioridad:** Alta

**Descripcion:**
El campo `percentage_invoices_on_time` muestra valores absurdos. Por ejemplo, "Drogueria Mixta SA" con 3 de 5 facturas a tiempo muestra 15.0 (1500%) en vez de 0.6 (60%), y su rating dice "Excellent" cuando deberia ser "Fair". Otro partner "Farmacia Nueva Express" con 4 de 4 facturas a tiempo muestra 16.0 en vez de 1.0.

**Pasos para reproducir:**
1. Ir a Contactos > "Drogueria Mixta SA"
2. Abrir la pestana "Payment Behavior"
3. Observar que el % muestra 15.0 en vez de 0.6, rating dice "Excellent" en vez de "Fair"
4. Verificar "Farmacia Nueva Express": muestra 16.0 en vez de 1.0

**Pista:** El problema esta en el metodo `_calculate_partner_payment_metrics` de `res_partner.py`. Revisa la formula de calculo del porcentaje.

**Contexto de negocio:** Con ratings invertidos, Cartera no gestiona a los clientes realmente malos y Comercial da cupos a quienes no los merecen.

---

### TICKET #5: "Credit Score Trend siempre muestra 'No History' en Enero"

**Reportado por:** Analista de Riesgo
**Prioridad:** Media

**Descripcion:**
El campo `credit_score_trend` de los credit scores de Enero siempre muestra "No History", aunque existan credit scores de Diciembre del anio anterior. El trend funciona bien para todos los demas meses (Feb-Dic).

**Pasos para reproducir:**
1. Verificar que existen credit scores para Diciembre 2025
2. Crear/ver el credit score de Enero 2026 para el mismo partner
3. Observar que el trend muestra "No History" en vez de comparar con Diciembre

**Pista:** Revisa la logica de `_compute_credit_score_trend` en `credit_score.py`. Que pasa cuando el mes actual es 1 (Enero)?

**Contexto de negocio:** Enero es el mes de revision anual de cupos. Con el trend roto, Riesgo no tiene comparativo del diciembre anterior — el mes de mayor volumen del anio.

---

### TICKET #6: "Credit scores dan resultados inconsistentes"

**Reportado por:** Gerente Financiero
**Prioridad:** Media

**Descripcion:**
Los credit scores no reflejan correctamente el comportamiento de pago. Un partner que paga el 95% de sus facturas a tiempo deberia tener un score alto, pero el score total sale mas bajo de lo esperado. Parece que los pesos de los componentes estan invertidos.

**Contexto del negocio:**
- El **Payment Behavior Score** (% de facturas a tiempo) deberia tener el MAYOR peso (60%) porque es el indicador mas directo de confiabilidad.
- El **Payment Timing Score** (velocidad promedio de pago) deberia tener peso secundario (40%).

**Pasos para reproducir:**
1. Tomar un partner con payment_behavior_score = 100 y payment_timing_score = 50
2. Calcular manualmente: (100 * 0.6) + (50 * 0.4) = 80 (deberia ser "Excellent")
3. Pero el sistema calcula: (100 * ?) + (50 * ?) = resultado diferente

**Contexto de negocio:** El score total es lo que Finanzas reporta a gerencia. Si los pesos estan al reves, el reporte pierde credibilidad ante la junta.

---

## PARTE 2: Nueva Funcionalidad (30 min)

### Feature: Agregar boton "Recalculate Payment Behavior" en la vista de facturas

**Requerimiento:**
Agregar un boton en el formulario de factura (account.move) que permita recalcular el comportamiento de pago del partner asociado. El boton debe:

1. Ser visible solo en facturas de tipo "Customer Invoice" (`out_invoice`)
2. Ser visible solo cuando la factura esta en estado "Posted"
3. Al hacer clic, ejecutar `_calculate_payment_behavior()` sobre el partner comercial
4. Mostrar una notificacion de exito al usuario
5. Solo usuarios del grupo `account.group_account_manager` deben ver el boton

**Entregable:**
- Codigo del boton en vista XML
- Metodo Python en el modelo `account.move`
- Restriccion de seguridad por grupo

---

## PARTE 3: Code Review (15 min)

Revisa el siguiente fragmento de codigo (hipotetico) que un companero quiere agregar al modulo. Identifica problemas y sugiere mejoras:

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'

    # New field to track payment risk level
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], string='Risk Level', compute='_compute_risk_level', store=True)

    @api.depends('percentage_invoices_on_time', 'average_pay_time', 'is_black_list')
    def _compute_risk_level(self):
        for partner in self:
            if partner.is_black_list:
                partner.risk_level = 'critical'
            elif partner.percentage_invoices_on_time < 0.5:
                partner.risk_level = 'high'
            elif partner.percentage_invoices_on_time < 0.7:
                partner.risk_level = 'medium'
            else:
                partner.risk_level = 'low'

    def action_send_risk_notification(self):
        template = self.env.ref('payment_behavior.email_template_risk_alert')
        for partner in self:
            template.send_mail(partner.id, force_send=True)
            partner.message_post(
                body=f"Risk notification sent to {partner.name}. Current level: {partner.risk_level}",
                message_type='notification'
            )
```

**Preguntas:**
1. Identifica al menos 3 problemas o mejoras en este codigo.
2. Que impacto tendria en produccion agregar el campo `risk_level` con `store=True` y `@api.depends`?
3. Que esta mal con el `message_post` en el contexto de Odoo i18n?
4. Como manejarias el envio masivo de emails para +50,000 partners?

---

## PARTE 4: Si fuera tu modulo, que le mejorarias? (15 min)

Despues de haber instalado, leido y arreglado el modulo, propon **entre 1 y 3 mejoras concretas**, con esta estructura para cada una:

- **Que** — descripcion en una o dos frases.
- **Por que** — que problema de negocio resuelve, a quien beneficia, que decision habilita.
- **Como** — sketch de implementacion (modelo, campo, cron, integracion, dashboard, etc.). Sin codigo, solo el enfoque.
- **Riesgo** — que tendrias que cuidar al implementarlo.

No buscamos la respuesta correcta. Buscamos que veas oportunidades de negocio en el codigo y propongas algo materializable. Una propuesta bien fundamentada vale mas que tres genericas.

Si no se te ocurre nada con suficiente fundamento, escribe exactamente eso. Es una respuesta valida.

---

## Entrega

Al finalizar, entregar:

1. **Los archivos modificados** (o un diff/patch).
2. **Un documento** (markdown o txt) con:
   - Por cada ticket: causa raiz + solucion + impacto en negocio.
   - Tu enfoque para la nueva funcionalidad.
   - Tu analisis del code review con respuestas a las 4 preguntas.
   - Tus propuestas de mejora (Parte 4) con la estructura pedida.
3. **Notas adicionales** sobre decisiones de diseno o trade-offs, si las hay.

---

## Notas finales

- **Tiempo**: 2 horas. Si no alcanzas todo, entrega lo que tengas. Tres tickets bien resueltos con contexto de negocio pesan mas que seis resueltos a medias.
- **Sin IA generativa**: puedes buscar documentacion, leer codigo OCA como referencia, consultar Stack Overflow. Lo que no puedes es pedirle a un LLM que resuelva los tickets por ti.
- **Honestidad sobre lo que no sabes**: si no encuentras la causa raiz de un ticket, documenta hasta donde llegaste y que hipotesis tienes. Eso tambien se evalua.
- **No refactorices lo que no esta roto**: cada fix debe ser quirurgico. Si tu diff tiene cambios que ningun ticket menciona, explica por que.
- **Lo que mas valoramos**: que entiendas para que sirve lo que estas arreglando, no solo que lo arregles.
