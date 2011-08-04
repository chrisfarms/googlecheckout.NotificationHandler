import base64
from google.appengine.ext import webapp
import logging
from xml.dom import minidom, Node

class DotDict(dict):
    """A dot-accessable dict-like object for accessing the checkout XML"""
    def __getattr__(self, attr):
        if attr in self:
            return self.get(attr, None)
        else:
            raise AttributeError("no attr %s" % (attr))
    @property
    def items(self):
        """more convient items access"""
        items_list = self['items'].get('item',[])
        if not isinstance(items_list, list):
            items_list = [items_list]
        return items_list
    __setattr__= dict.__setitem__
    __delattr__= dict.__delitem__
    
def node_to_dotdict(self):
    """The google XML format is very simple so we can easily convert the 
    whole thing into a big dict. this function returns a DotDict
    repeated values are converted to lists"""
    d = DotDict()
    for node in self.childNodes:
        if node.nodeType == Node.TEXT_NODE and node.nodeValue.strip():
            return node.nodeValue
        elif node.nodeType == Node.ELEMENT_NODE:
            name = node.nodeName.replace('-','_')
            value = node_to_dotdict(node)
            if name in d and isinstance(getattr(d,name),(dict,basestring,list)):
                if isinstance(d[name],list):
                    d[name].append(value)
                else:
                    d[name] = [d[name], value]
            else:
                d[name] = value
    return d

def xml_to_dotdict(xmlstr):
    dom = minidom.parseString(xmlstr)
    return node_to_dotdict(dom.documentElement)

class Error(Exception):
    """Base class for exceptions in this module."""

class IgnoreNotification(Error):
    """Base class for exceptions raised to ackknowledge 
    by not do anything with a notificaiton"""
    
def get_list_from_value(notification_value):
    "Checks to see if value in notification dict is a list or unicode. Returns list of value(s) as integers."
    if type(notification_value) == list:
        return [ int(x) for x in notification_value ]
    else: return [int(notification_value)]
    

    
class NotificationHandler(webapp.RequestHandler):
    """A base RequestHandler handler class for implimenting the google-checkout notification API.

    Create a webapp handler by subclassing the NotificationHandler defining a merchant_details 
    method and overriding any notification methods you wish to use:

        class MyNotificationHandler(NotificationHandler)
    
            def merchant_details():
                "return a tuple of your merchant details"
                return (your_id, your_key)
            
            def new_order(self):
                logging.info("got a new order notification", self.notification)

    By default NotificationHandler silently accepts all notifications and leaves a 
    message in the log. It expects that you will overide one or more of the following methods
    in your Handler:
    
        class MyNotificationHandler(NotificationHandler)
        
            new_order(self):
                "Do something with the new-order-notification"

            def risk_information(self):
                "Do something with the risk-information-notification"

            def order_state_change(self):
                "Do something with the order-state-change-notification"

            def charge_amount(self):
                "Do something with the charge-amount-notification"

    Within the context of a NotificationHandler self.notification contains a dict-like object
    with all the notification values that can be found at:
    http://code.google.com/apis/checkout/developer/Google_Checkout_XML_API_Notification_API.html#Types_of_Notifications

    The values in self.notifications are pythonized by converting "-" to "_". So 'order-summary' becomes 'order_summary'
    This allows you to access the values via dot-notation. For example:

        self.notification.order_summary.google_order_number # contains the order reference

    As a full example, if we have a simple Order model to store our new order details
    we could then make a notification handler

        class Order(db.Model):
            amount = db.StringProperty()
            paid = db.StringProperty()
            name = db.StringProperty()
            email = db.StringProperty()
            address_line_1 = StringProperty()
            city = StringProperty()
            postcode = StringProperty()
            phone = StringProperty()
            items = db.StringListProperty()

        class MyNotificationHandler(notification_handler('your-merchant-id','your-merchant-key')):
            "An example notifcation handle"

            def merchant_details():
                "return a tuple of your merchant details"
                return ("12345678910", "Axoiuyfq2309230f9u2gf")
                
            def new_order(self):
                "Create an order for the incoming order notification"
                # first check if we already created this order (maybe the notification can in twice
                order = Order.all().get_by_key_name(self.notification.google_order_number)
                if order:
                    return
                # otherwise create an order
                order = Order(
                    key_name       = self.notification.google_order_number,
                    name           = self.notification.buyer_shipping_address.contact_name,
                    email          = self.notification.buyer_shipping_address.email,
                    address_line_1 = self.notification.buyer_shipping_address.address1,
                    city           = self.notification.buyer_shipping_address.city,
                    postcode       = self.notification.buyer_shipping_address.postal_code,
                    amount         = self.notification.order_total,
                    phone          = self.notification.buyer_shipping_address.phone)
                # record each item in the order
                for item in self.notification.shopping_cart.items:
                    order.items.append( item.item_name )
                order.put()

            def charge_amount(self):
                "Mark a previous order as paid"
                order = Order.all().get_by_key_name(self.notification.google_order_number)
                order.paid = True
                order.put()

    any exceptions raised during execution of the notification will result in the notification being resent
    from google-checkout.

    raise IgnoreNotification if you wish to raise an exception and also return send an OK ackknowledgement to
    google-checkout to prevent re-sending.
    """
    
    def merchant_details(self):
        "Return tuple of (merchant_id,merchant_key)"
        raise Error("Missing merchant details. define a %s.merchant_details method to return a tuple of (merchant_id,merchant_key)", self.__class__.__name__)
    
    def _parse_notification(self): 
        "All google notifications are parsed and categorized by type."
        dom = minidom.parseString(self.request.body)
        # store the notification type
        self.notification_type = dom.childNodes[0].localName 
        # convert the xml to a more python friendly format (a dict with dot-access)
        self.notification = node_to_dotdict(dom.documentElement)
        # get the serial number
        try:
            self.notification_serial_number = dom.childNodes[0].attributes["serial-number"].value
        except KeyError:
            logging.error("GoogleNotification: notification body did not contain a serial-number field")
            raise
        
    def _handshake(self):
        "Acknowledge receipt of notification."
        doc = minidom.Document() 
        ack = doc.createElement("notification-acknowledgment")
        ack.setAttribute("xmlns","http://checkout.google.com/schema/2")
        ack.setAttribute("serial-number", self.notification_serial_number)
        doc.appendChild(ack)
        # return full acknowledgment
        self.response.headers['Content-Type'] = 'text/xml'
        self.response.out.write( doc.toxml(encoding="utf-8") )

    def _check_request(self):
        "Check to ensure valid Google notification."
        if not self.request.headers.get('Authorization'):
            logging.error("GoogleNotification: incoming notification had no Authorization header")
            return self.error(401)            
        #get the Authorization string from the Google POST header         
        auth_string = self.request.headers.get('Authorization')       
        #decode the Authorization string and remove Basic portion
        plain_string = base64.b64decode(auth_string.lstrip('Basic '))
        #split the decoded string at the ':'
        merchant_id, merchant_key = plain_string.split(':')
        # check credentials
        our_merchant_id,our_merchant_key = self.merchant_details()
        if merchant_id != our_merchant_id or merchant_key != our_merchant_key:
            logging.error("GoogleNotification: incoming notification had unexpected merchant id and/or key")
            return self.error(401)
        # check body exits
        if not self.request.body:
            logging.error("GoogleNotification: incoming notification had no request body")
            return self.error(400)
        # everything looks ok
        return True

    def new_order(self):
        self.unhandled_notification()

    def risk_information(self):
        self.unhandled_notification()

    def order_state_change(self):
        self.unhandled_notification()

    def charge_amount(self):
        self.unhandled_notification()
        
    def chargeback_amount(self):
        self.unhandled_notification()
        
    def refund_amount(self):
        self.unhandled_notification()
        
    def authorization_amount(self):
        self.unhandled_notification()

    def unhandled_notification(self):
        raise IgnoreNotification("GoogleNotification: %s received but ignored" %  self.notification_type)
            
    def _process_notification(self):
        "call the apropriate method for each notification type"
        if self.notification_type == 'new-order-notification': #new order
            self.new_order()
        elif self.notification_type == 'risk-information-notification':
            self.risk_information()
        elif self.notification_type == 'order-state-change-notification':
            self.order_state_change()
        elif self.notification_type == 'charge-amount-notification':
            self.charge_amount()
        elif self.notification_type == 'authorization-amount-notification':
            self.authorization_amount()
        elif self.notification_type == 'refund-amount-notification':
            self.refund_amount()
        elif self.notification_type == 'chargeback-amount-notification':
            self.chargeback_amount()
        else: #all other notifications are ignored    
            self.unhandled_notification()
            
    def post(self): 
        if not self._check_request():
            logging.error("GoogleNotification: invalid")
            return
        # parse/init notification request
        self._parse_notification()
        # try to call process notification method
        try:
            self._process_notification()
        except IgnoreNotification, e:
            # if IgnoreNotification is raised, the handshake will be completed
            # so google will not retry the notifcation in the future. all handler
            # methods raise this by default
            logging.info(str(e))
        self._handshake()
