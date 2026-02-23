# Prueba Tecnica - Desarrollador Odoo Senior

**Empresa:** M&S VITAMINS SAS
**Modulo:** Payment Behavior (Odoo 14)
**Duracion:** 2 horas maximo
**Herramientas permitidas:** Claude Code, Copilot, ChatGPT, documentacion online, etc.

---

## Contexto

Eres un nuevo desarrollador en M&S VITAMINS. Tu primer dia recibes varios tickets de soporte relacionados con el modulo **Payment Behavior**, que analiza el comportamiento de pago de los clientes.

El modulo:
- Calcula metricas de pago por partner (promedio de dias, % a tiempo, rating)
- Genera credit scores mensuales
- Detecta clientes morosos (blacklist)
- Se actualiza en tiempo real (hook de reconciliacion) y por cron diario (batch SQL)

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

Resuelve los siguientes tickets. Para cada uno:
1. Identifica la causa raiz
2. Implementa la solucion
3. Documenta brevemente que hiciste y por que

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

**Impacto:** Las metricas de comportamiento de pago son incorrectas para clientes que pagan en cuotas.

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

---

### TICKET #3: "Timeout al actualizar modulo en produccion"

**Reportado por:** DevOps
**Prioridad:** Critica

**Descripcion:**
Al hacer upgrade del modulo en la base de datos de produccion (que tiene +50,000 partners), el proceso se queda colgado por mas de 30 minutos y eventualmente da timeout.

El error ocurre porque Odoo intenta calcular los campos `payment_status` y `payment_behavior_rating` para TODOS los partners existentes al mismo tiempo durante la instalacion.

**Contexto tecnico:**
- En Odoo, cuando se agrega un campo `stored computed` o un campo `Selection` con `store=True` a un modelo existente, el sistema intenta computar/inicializar el valor para todos los registros existentes
- Esto causa un problema masivo de rendimiento con +50,000 registros

**Pista:** Investiga como otros modulos de Odoo manejan la inicializacion de columnas con `_auto_init()` y funciones de `odoo.tools.sql`.

---

### TICKET #4: "Todos los partners aparecen como 'Very Poor' aunque pagan bien"

**Reportado por:** Equipo de Cartera
**Prioridad:** Alta

**Descripcion:**
El campo `percentage_invoices_on_time` muestra valores absurdos para los partners. Por ejemplo, "Drogueria Mixta SA" con 3 de 5 facturas a tiempo muestra 15.0 (1500%) en vez de 0.6 (60%), y su rating dice "Excellent" cuando deberia ser "Fair". Otro partner "Farmacia Nueva Express" con 4 de 4 facturas a tiempo muestra 16.0 en vez de 1.0.

**Pasos para reproducir:**
1. Ir a Contactos > "Drogueria Mixta SA"
2. Abrir la pestana "Payment Behavior"
3. Observar que el % muestra 15.0 en vez de 0.6, rating dice "Excellent" en vez de "Fair"
4. Verificar "Farmacia Nueva Express": muestra 16.0 en vez de 1.0

**Pista:** El problema esta en el metodo `_calculate_partner_payment_metrics` de `res_partner.py`. Revisa la formula de calculo del porcentaje.

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

---

### TICKET #6: "Credit scores dan resultados inconsistentes"

**Reportado por:** Gerente Financiero
**Prioridad:** Media

**Descripcion:**
Los credit scores no reflejan correctamente el comportamiento de pago. Un partner que paga el 95% de sus facturas a tiempo deberia tener un score alto, pero el score total sale mas bajo de lo esperado. Parece que los pesos de los componentes estan invertidos.

**Contexto del negocio:**
- El **Payment Behavior Score** (% de facturas a tiempo) deberia tener el MAYOR peso (60%) porque es el indicador mas directo de confiabilidad
- El **Payment Timing Score** (velocidad promedio de pago) deberia tener peso secundario (40%)

**Pasos para reproducir:**
1. Tomar un partner con payment_behavior_score = 100 y payment_timing_score = 50
2. Calcular manualmente: (100 * 0.6) + (50 * 0.4) = 80 (deberia ser "Excellent")
3. Pero el sistema calcula: (100 * ?) + (50 * ?) = resultado diferente

---

## PARTE 2: Nueva Funcionalidad (40 min)

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

## PARTE 3: Code Review (20 min)

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

**Preguntas para el candidato:**
1. Identifica al menos 3 problemas o mejoras en este codigo
2. Que impacto tendria en produccion agregar el campo `risk_level` con `store=True` y `@api.depends`?
3. Que esta mal con el `message_post` en el contexto de Odoo i18n?
4. Como manejarias el envio masivo de emails para +50,000 partners?

---

## Entrega

Al finalizar, entregar:
1. Los archivos modificados (o un diff/patch)
2. Un documento breve (puede ser un .md o .txt) explicando:
   - Que bugs encontraste y como los solucionaste
   - Tu enfoque para la nueva funcionalidad
   - Tu analisis del code review
3. Cualquier nota adicional sobre decisiones de diseno

---

## Notas Finales

- Se espera que uses herramientas de IA para ser mas productivo, no para que hagan todo por ti.
- Se valorara la calidad del codigo, el uso de patrones Odoo y la documentacion clara.
