# -*- coding: utf-8 -*-
# Copyright (C) 2016 KMEE (http://www.kmee.com.br)
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
import time

from datetime import datetime
from openerp import api, models, fields, exceptions, _
from openerp.tools import float_compare
from lxml import etree

NOME_LANCAMENTO_LOTE = {
    'provisao_ferias': u'Provisão de Férias em Lote',
    'adiantamento_13': u'Décimo Terceiro Salário em Lote',
    'provisao_decimo_terceiro': u'Provisão de 13 em Lote',
    'normal': u'Folha normal em Lote',
}


class RubricaContabiliza(object):
    def __init__(self):
        self.line = None
        self.total = 0
        self.name = ''


class L10nBrHrPayslip(models.Model):
    _inherit = 'hr.payslip.run'

    @api.model
    def _buscar_diario_fopag(self):
        if self.env.context.get('params'):
            return self.env.ref(
                "l10n_br_hr_payroll_account.payroll_account_journal").id
        return self.env["account.journal"]

    @api.multi
    def _buscar_lancamentos(self):
        for payslip_run in self:
            if payslip_run.id:
                payslip_run.move_lines_id = \
                    self.env['account.move.line'].search(
                        [
                            ('payslip_run_id', '=', payslip_run.id)
                        ]
                    )

    provisao_ferias_account_debit = fields.Many2one(
        comodel_name='account.account',
        string='Conta débito provisão de Férias',
    )
    provisao_ferias_account_credit = fields.Many2one(
        comodel_name='account.account',
        string='Conta crédito provisão de Férias',
    )

    provisao_13_account_debit = fields.Many2one(
        comodel_name='account.account',
        string='Conta débito provisão Décimo 13º',
    )
    provisao_13_account_credit = fields.Many2one(
        comodel_name='account.account',
        string='Conta crédito provisão Décimo 13º',
    )
    holerite_normal_account_debit = fields.Many2one(
        comodel_name='account.account',
        string='Conta débito holerite normal',
    )
    holerite_normal_account_credit = fields.Many2one(
        comodel_name='account.account',
        string='Conta crédito holerite normal',
    )
    decimo_13_account_debit = fields.Many2one(
        comodel_name='account.account',
        string='Conta débito Décimo 13º',
    )
    decimo_13_account_credit = fields.Many2one(
        comodel_name='account.account',
        string='Conta crédito Décimo 13º',
    )

    move_id = fields.One2many(
        comodel_name='account.move',
        inverse_name='payslip_run_id',
        string='Movimentações Contábeis',
    )

    move_lines_id = fields.One2many(
        comodel_name='account.move.line',
        string=u'Lançamentos',
        compute=_buscar_lancamentos,
    )

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string=u"Diário",
        default=_buscar_diario_fopag
    )

    @api.multi
    def _buscar_contas_lotes(self):
        if self.tipo_de_folha == "normal":
            return self.holerite_normal_account_debit, self.\
                holerite_normal_account_credit
        elif self.tipo_de_folha in ["decimo_terceiro",'adiantamento_13']:
            return self.decimo_13_account_debit, self.\
                decimo_13_account_credit
        elif self.tipo_de_folha == "provisao_ferias":
            return self.provisao_ferias_account_debit, self.\
                provisao_ferias_account_credit
        elif self.tipo_de_folha == "provisao_decimo_terceiro":
            return self.provisao_13_account_debit, self.\
                provisao_13_account_credit
        else:
            return False, False

    @api.multi
    def _verificar_lancamentos_lotes_anteriores(self, tipo_folha, period_id):
        period_obj = self.env['account.period']

        for payslip in self:

            # Calcular o mês/ano anterior
            mes_anterior = payslip.mes_do_ano - 1
            ano_anterior = payslip.ano
            if mes_anterior == 0:
                mes_anterior = 12
                ano_anterior -= 1

            primeiro_dia_do_mes = str(
                datetime.strptime(str(mes_anterior) + '-' +
                                  str(ano_anterior), '%m-%Y'))

            # Encontrar o Período anterior
            periodo_anterior_id = period_obj.find(primeiro_dia_do_mes)

            # Encontrar o Lote anterior
            lote_anterior = self.env['hr.payslip.run'].search(
                [
                    ('mes_do_ano', '=', mes_anterior),
                    ('ano', '=', ano_anterior),
                    ('company_id', '=', payslip.company_id.id),
                    ('tipo_de_folha', '=', payslip.tipo_de_folha)
                ]
            )

            if lote_anterior:
                move_ids = self.env['account.move'].search(
                    [
                        ('ref', 'like', lote_anterior.display_name),
                        ('period_id', '=', periodo_anterior_id.id),
                        ('payslip_run_id', '!=', False),
                    ],
                )

                # Se for provisão de 13º e o mês anterior for Dezembro, não deve
                # desfazer os lançamentos anteriores
                #
                if tipo_folha == 'provisao_13' and mes_anterior == 12:
                    return False

                return move_ids
            else:
                return False

    @api.multi
    def _valor_lancamento_lote_anterior_rubrica(self, rubrica):
        if self.tipo_de_folha in ["normal", 'adiantamento_13']:
            return \
                rubrica.salary_rule_id.holerite_normal_account_debit, \
                rubrica.salary_rule_id.holerite_normal_account_credit
        if self.tipo_de_folha == "ferias":
            return \
                rubrica.salary_rule_id.ferias_account_debit, \
                rubrica.salary_rule_id.ferias_account_credit
        if self.tipo_de_folha in ["decimo_terceiro"]:
            return \
                rubrica.salary_rule_id.decimo_13_account_debit, \
                rubrica.salary_rule_id.decimo_13_account_credit
        if self.tipo_de_folha == "rescisao":
            return \
                rubrica.salary_rule_id.rescisao_account_debit, \
                rubrica.salary_rule_id.rescisao_account_credit
        if self.tipo_de_folha == "provisao_ferias":
            return \
                rubrica.salary_rule_id.provisao_ferias_account_debit, \
                rubrica.salary_rule_id.provisao_ferias_account_credit
        if self.tipo_de_folha == "provisao_decimo_terceiro":
            return \
                rubrica.salary_rule_id.provisao_13_account_debit, \
                rubrica.salary_rule_id.provisao_13_account_credit

    @api.multi
    def _verificar_existencia_conta_rubrica(self, rubrica, tipo_de_folha):
        if tipo_de_folha == "provisao_ferias":
            if rubrica.provisao_ferias_account_debit or \
                    rubrica.provisao_ferias_account_credit:
                return True
        elif tipo_de_folha == "provisao_decimo_terceiro":
            if rubrica.provisao_13_account_debit or \
                    rubrica.provisao_13_account_credit:
                return True
        elif tipo_de_folha in ["normal", 'adiantamento_13']:
            if rubrica.holerite_normal_account_debit or \
                    rubrica.holerite_normal_account_credit:
                return True
        elif tipo_de_folha in ['decimo_terceiro']:
            if rubrica.decimo_13_account_debit or \
                    rubrica.decimo_13_account_credit:
                return True
        else:
            return False

    @api.multi
    def processar_folha(self):
        if self.journal_id:
            rubricas = {}
            for payslip_run in self:
                for payslip in self.slip_ids:
                    for line in payslip.details_by_salary_rule_category:
                        # Verificar se na rubrica, o cadastro das contas para
                        # debito e credito estao OK
                        if payslip_run._verificar_existencia_conta_rubrica(
                                line.salary_rule_id,
                                payslip_run.tipo_de_folha
                        ):
                            if not rubricas.get(line.salary_rule_id.id):
                                rubrica = RubricaContabiliza()
                                rubrica.line = line
                                rubrica.total = line.total
                                rubrica.name = line.name
                                rubricas.update(
                                    {line.salary_rule_id.id: rubrica}
                                )
                            else:
                                rubricas[line.salary_rule_id.id].total += \
                                    line.total
                self.processar_contabilidade_folha(rubricas)
        else:
            raise exceptions.Warning(
                ("Erro!"),
                ("É preciso selecionar um diário para realizar "
                 "a contabilização!")
            )

    @api.multi
    def processar_contabilidade_folha(self, rubricas):
        """        
        :param rubricas: 
        :return: 
        """
        for payslip_run in self:
            move_obj = self.env['account.move']
            period_obj = self.env['account.period']
            precision = self.env['decimal.precision'].precision_get('Payroll')

            timenow = time.strftime('%Y-%m-%d')
            period_id = period_obj.find(payslip_run.date_start)
            debit_sum = 0.0
            credit_sum = 0.0
            contador_lancamentos = 1

            # Exclui o lançamento se já existir
            if payslip_run.move_id:
                payslip_run.move_id.unlink()

            for rubrica in rubricas:
                line_ids = []
                move = False

                if rubricas[rubrica].total > 0:
                    move = self.criar_lancamento_contabil(
                        line_ids, payslip_run, period_id,
                        timenow, contador_lancamentos
                    )
                    contador_lancamentos += 1
                    debito, credito = \
                        self._valor_lancamento_lote_anterior_rubrica(
                            rubricas[rubrica].line
                        )

                    if credito:
                        credit_line = (0, 0, {
                            'name': rubricas[rubrica].name,
                            'date': timenow,
                            'account_id': credito.id,
                            'journal_id': payslip_run.journal_id.id,
                            'period_id': period_id.id,
                            'debit': 0.0,
                            'credit': rubricas[rubrica].total,
                            'payslip_run_id': payslip_run.id,
                        })
                        line_ids.append(credit_line)
                        credit_sum += \
                            credit_line[2]['credit'] - credit_line[2][
                                'debit']
                    if debito:
                        debit_line = (0, 0, {
                            'name': rubricas[rubrica].name,
                            'date': timenow,
                            'account_id': debito.id,
                            'journal_id': payslip_run.journal_id.id,
                            'period_id': period_id.id,
                            'debit': rubricas[rubrica].total,
                            'credit': 0.0,
                            'payslip_run_id': payslip_run.id,
                        })
                        line_ids.append(debit_line)
                        debit_sum += \
                            debit_line[2]['debit'] - debit_line[2][
                                'credit']
                if float_compare(
                        credit_sum, debit_sum, precision_digits=precision
                ) == -1:
                    adjust_credit = (0, 0, {
                        'name': _('Adjustment Entry'),
                        'date': timenow,
                        'partner_id': False,
                        'account_id': conta_credito.id,
                        'journal_id': payslip_run.journal_id.id,
                        'period_id': period_id.id,
                        'debit': 0.0,
                        'credit': debit_sum - credit_sum,
                        'payslip_run_id': payslip_run.id,
                    })
                    line_ids.append(adjust_credit)
                elif float_compare(
                        debit_sum, credit_sum, precision_digits=precision
                ) == -1:
                    adjust_debit = (0, 0, {
                        'name': _('Adjustment Entry'),
                        'date': timenow,
                        'partner_id': False,
                        'account_id': conta_debito.id,
                        'journal_id': payslip_run.journal_id.id,
                        'period_id': period_id.id,
                        'debit': credit_sum - debit_sum,
                        'credit': 0.0,
                        'payslip_run_id': payslip_run.id
                    })
                    line_ids.append(adjust_debit)
                if move:
                    move.update({'line_id': line_ids})
                    move_id = move_obj.create(move)
                    # if not payslip_run.move_id:
                    #     move.update({'line_id': line_ids})
                    #     move_id = move_obj.create(move)
                    # else:
                    #     for line in line_ids:
                    #         line[2].update({'move_id': payslip_run.move_id.id})
                    #         self.env['account.move.line'].create(line[2])
                    #     move_id = payslip_run.move_id
                if payslip_run.journal_id.entry_posted:
                    move_obj.post(move_id)

            #
            # Se não for a contabilização do lote de alguma provisão
            # Não precisa Desfazer lançamentos do mês anterior
            #

            if payslip_run.tipo_de_folha not in ['provisao_ferias', 'provisao_decimo_terceiro']:
                return

            # Identificar os lançamentos do mês anterior
            #
            move_anterior_ids = \
                self._verificar_lancamentos_lotes_anteriores(
                    payslip_run.tipo_de_folha, period_id.id,
                )

            # Rodar todos os lançamentos do mês anterior e criar um movimento
            # reverso para cada um
            #
            if move_anterior_ids:
                for movimento in move_anterior_ids:

                    name = \
                        NOME_LANCAMENTO_LOTE[payslip_run.tipo_de_folha] + \
                        " - " + str(payslip_run.mes_do_ano) + \
                        "/" + str(payslip_run.ano) + " - " + \
                        str("%03d" % contador_lancamentos)
                    move = {
                        'name': name,
                        'display_name': name,
                        'narration': name,
                        'date': payslip_run.date_end,
                        'ref': payslip_run.display_name,
                        'journal_id': payslip_run.journal_id.id,
                        'period_id': period_id.id,
                        'payslip_run_id': payslip_run.id,
                    }
                    contador_lancamentos += 1

                    line_ids = []

                    for linha in movimento.line_id:
                        if "(Anterior)" not in linha.name:
                            line_anterior = (0, 0, {
                                'name': linha.name + " (Anterior)",
                                'date': timenow,
                                'account_id': linha.account_id.id,
                                'journal_id': linha.journal_id,
                                'period_id': period_id,
                                'debit': linha.credit if linha.credit else 0.0,
                                'credit': linha.debit if linha.debit else 0.0,
                                'payslip_run_id': payslip_run.id,
                            })
                            line_ids.append(line_anterior)

                    move.update({'line_id': line_ids})
                    move_id = move_obj.create(move)

    def criar_lancamento_contabil(self, line_ids, payslip_run, period_id,
                                  timenow, contador_lancamento):
        # Cria o lançamento do zero
        name = \
            NOME_LANCAMENTO_LOTE[payslip_run.tipo_de_folha] + \
            " - " + str(payslip_run.mes_do_ano) + \
            "/" + str(payslip_run.ano) + " - " + \
            str("%03d" % contador_lancamento)

        move = {
            'name': name,
            'display_name': name,
            'narration': name,
            'date': payslip_run.date_end,
            'ref': payslip_run.display_name,
            'journal_id': payslip_run.journal_id.id,
            'period_id': period_id.id,
            'payslip_run_id': payslip_run.id,
        }
        return move

    @api.model
    def fields_view_get(self, view_id=None, view_type='form',
                        toolbar=False, submenu=False):
        res = super(L10nBrHrPayslip, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar,
            submenu=submenu
        )
        if view_type == 'form':
            doc = etree.XML(res['arch'])
            for sheet in doc.xpath("//sheet"):
                parent = sheet.getparent()
                index = parent.index(sheet)
                for child in sheet:
                    parent.insert(index, child)
                    index += 1
                parent.remove(sheet)
            res['arch'] = etree.tostring(doc)
        return res
