# -*- Mode: Python; coding: iso-8859-1 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
## USA.
##
## Author(s):   Evandro Vale Miquelito      <evandro@async.com.br>
##
"""
stoq/gui/wizards/sale.py:

    Sale wizard definition
"""

import gettext

from stoqlib.gui.dialogs import run_dialog
from stoqlib.gui.wizards import BaseWizardStep, BaseWizard

from stoq.gui.search.person import ClientSearch
from stoq.gui.slaves.sale import DiscountChargeSlave
from stoq.gui.slaves.payment import (CheckMethodSlave, BillMethodSlave, 
                                     CardMethodSlave, 
                                     FinanceMethodSlave)
from stoq.lib.parameters import sysparam
from stoq.lib.validators import get_price_format_str
from stoq.domain.person import Person
from stoq.domain.sale import Sale
from stoq.domain.payment.base import AbstractPaymentGroup
from stoq.domain.interfaces import (IPaymentGroup, ISalesPerson, IClient,
                                    ICheckPM, ICardPM, IBillPM, 
                                    IFinancePM)
_ = gettext.gettext


#
# Wizard Steps
#


class PaymentMethodStep(BaseWizardStep):
    gladefile = 'PaymentMethodStep'
    model_type = Sale
    slave_holder = 'method_holder'
    widgets = ('method_combo',)

    def __init__(self, wizard, previous, conn, model):
        # A dictionary for payment method informaton. Each key is a
        # PaymentMethod adapter and its value is a tuple where the first
        # element is a payment method interface and the second one is the
        # slave class
        self.method_dict = {}
        # A cache for instantiated slaves
        self.slaves_dict = {}
        BaseWizardStep.__init__(self, conn, wizard, model, previous)
        self.method_slave = None
        self.setup_combo()
        self._update_payment_method_slave()

    def _set_method_slave(self, slave_class, slave_args):
        if not self.slaves_dict.has_key(slave_class):
            slave = slave_class(*slave_args)
            self.slaves_dict[slave_class] = slave
        else:
            slave = self.slaves_dict[slave_class]
        self.method_slave = slave

    def _update_payment_method_slave(self):
        selected = self.method_combo.get_selected_data()
        group = self.wizard.get_payment_group()
        slave_args = self.wizard, self, self.conn, self.model, selected
        if not self.method_dict.has_key(selected):
            raise ValueError('Invalid payment method type: %s' 
                             % type(selected))
        iface, slave_class = self.method_dict[selected]
        group.set_method(iface)
        self._set_method_slave(slave_class, slave_args)
        
        if self.get_slave(self.slave_holder):
            self.detach_slave(self.slave_holder)
        self.attach_slave(self.slave_holder, self.method_slave)

    def setup_combo(self):
        slaves_info = ((ICheckPM, CheckMethodSlave),
                       (IBillPM, BillMethodSlave),
                       (ICardPM, CardMethodSlave),
                       (IFinancePM, FinanceMethodSlave))
        base_method = sysparam(self.conn).BASE_PAYMENT_METHOD
        combo_items = []
        for iface, slave_class in slaves_info:
            method = iface(base_method, connection=self.conn)
            if method.is_active:
                self.method_dict[method] = iface, slave_class
                combo_items.append((method.description, method))
        self.method_combo.prefill(combo_items)

    #
    # WizardStep hooks
    #

    def next_step(self):
        self.method_slave.finish()
        return CustomerStep(self.wizard, self, self.conn, self.model)


    def post_init(self):
        self.method_combo.grab_focus()
        if self.method_slave:
            self.method_slave.update_view()

    #
    # Kiwi callbacks
    #

    def on_method_combo__changed(self, *args):
        self._update_payment_method_slave()


class CustomerStep(BaseWizardStep):
    gladefile = 'CustomerStep'
    model_type = Sale
    proxy_widgets = ('client', 
                     'order_number',
                     'order_details', 
                     'order_total_lbl')

    def __init__(self, wizard, previous, conn, model):
        BaseWizardStep.__init__(self, conn, wizard, model, previous)
        self.register_validate_function(self.wizard.refresh_next)

    def setup_entry_completion(self):
        table = Person.getAdapterClass(IClient)
        clients = table.get_active_clients(self.conn)
        strings = [c.get_adapted().name for c in clients]
        self.client.set_completion_strings(strings, list(clients))

    def update_view(self):
        # TODO Check here if the customer data has enough information like
        # cpf or phone_number according to parameter value. Bug 2172
        pass

    def _setup_widgets(self):
        self.setup_entry_completion()
        self.order_total_lbl.set_data_format(get_price_format_str())
    
    #
    # BaseEditorSlave hooks
    #

    def setup_proxies(self):
        self._setup_widgets()
        self.proxy = self.add_proxy(self.model,
                                    CustomerStep.proxy_widgets)

    #
    # WizardStep hooks
    #

    def post_init(self):
        self.client.grab_focus()
        self.client_hbox.set_focus_chain([self.client])
        self.order_details.set_accepts_tab(False)
        self.update_view()

    def has_next_step(self):
        return False

    #
    # Kiwi callbacks
    #

    def on_add_button__clicked(self, *args):
        # XXX Ops, we can commit self.conn if we send it to ClientSearch. 
        # Unfortunately there is no alway around this to allow us gettting a
        # new customer in another transaction. We will fix this problem in
        # another bug.
        person = run_dialog(ClientSearch, self, parent_conn=self.conn)
        if person:
            self.model.update_client(person)


class SalesPersonStep(BaseWizardStep):
    gladefile = 'SalesPersonStep'
    model_type = Sale
    slave_holder = 'discount_charge_slave'
    proxy_widgets = ('total_lbl', 
                     'subtotal_lbl',
                     'salesperson_combo')
    widgets = proxy_widgets + ('cash_check', 
                               'subtotal_expander',
                               'othermethods_check')

    def __init__(self, wizard, conn, model, edit_mode):
        self.discount_charge_slave = DiscountChargeSlave(conn, model,
                                                         self.model_type)
        BaseWizardStep.__init__(self, conn, wizard, model)
        if edit_mode:
            group = IPaymentGroup(self.model, connection=self.conn)
            if not group:
                raise ValueError('You should have a IPaymentGroup facet '
                                 'defined at this point')
            if group.default_method == AbstractPaymentGroup.METHOD_MONEY:
                self.cash_check.set_active(True)
            else:
                self.othermethods_check.set_active(True)
        else:
            model.reset_discount_and_charge()
        self.register_validate_function(self.previous.refresh_next)
        changed_handler = self.update_totals
        if self.get_slave(self.slave_holder):
            self.detach_slave(self.slave_holder)
        self.attach_slave(self.slave_holder, self.discount_charge_slave)

    def update_totals(self):
        for field_name in ('total_sale_amount', 'sale_subtotal'):
            self.proxy.update(field_name)

    def setup_combo(self):
        table = Person.getAdapterClass(ISalesPerson)
        salespersons = table.select(connection=self.conn)
        items = [(s.get_adapted().name, s) for s in salespersons]
        self.salesperson_combo.prefill(items)

    def setup_cash_payment(self):
        money_method = sysparam(self.conn).METHOD_MONEY
        group = self.previous.get_payment_group()
        total = group.get_total_received()
        # For cash we only have one installment always
        inst_number = money_method.get_max_installments_number()
        money_method.setup_inpayments(total, group, inst_number)

    def on_discount_charge_slave__discount_changed(self, slave):
        self.update_totals()

    def _setup_widgets(self):
        self.setup_combo()
        self.total_lbl.set_data_format(get_price_format_str())
        self.subtotal_lbl.set_data_format(get_price_format_str())


    #
    # WizardStep hooks
    #

    def post_init(self):
        self.salesperson_combo.grab_focus()
        
    def next_step(self):
        has_cash = self.cash_check.get_active()
        if self.wizard.skip_payment_step:
            group = self.wizard.get_payment_group()
            if has_cash:
                group.default_method = AbstractPaymentGroup.METHOD_MONEY
            else:
                group.default_method = AbstractPaymentGroup.METHOD_MULTIPLE

        if has_cash:
            self.setup_cash_payment()
            step_class = CustomerStep
        elif not self.wizard.skip_payment_step:
            step_class = PaymentMethodStep
        else:
            step_class = CustomerStep
        return step_class(self.previous, self, self.conn, self.model)

    def has_previous_step(self):
        return False

    #
    # BaseEditorSlave hooks
    #

    def setup_proxies(self):
        self._setup_widgets()
        self.proxy = self.add_proxy(self.model,
                                    SalesPersonStep.proxy_widgets)


#
# Main wizard
#


class SaleWizard(BaseWizard):
    size = (600, 400)
    
    def __init__(self, conn, model, title=_('Sale Checkout'),
                 edit_mode=False, skip_payment_step=False):
        self.title = title
        self.skip_payment_step = skip_payment_step
        first_step = SalesPersonStep(self, conn, model, edit_mode)
        BaseWizard.__init__(self, conn, first_step, model,
                            edit_mode=edit_mode)
        group = self.get_payment_group()
        group.clear_preview_payments()

    #
    # WizardStep hooks
    #

    def finish(self):
        if not sysparam(self.conn).CONFIRM_SALES_ON_TILL:
            self.model.confirm_sale()
        else:
            self.model.validate()
            # TODO We should here update the stocks and mark them as 
            # reserved for this sale. Lets do it in another bug
        self.retval = True
        self.close()

    #
    # Auxiliar methods
    #

    def get_payment_group(self):
        group = IPaymentGroup(self.model, connection=self.conn)
        if not group:
            group = self.model.addFacet(IPaymentGroup,
                                        connection=self.conn)
        return group
